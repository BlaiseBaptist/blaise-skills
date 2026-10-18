#!/usr/bin/env python3
"""Control real T3 threads via fleet SSH and T3 0.1.0's local server API.

Enforces the fleet's delegation rules: only Opus and Sol delegate, and max effort
is never used. When the
child finishes, its parent's T3 thread gets a message.

No third-party dependencies, stored credentials, or T3 source changes.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


# Only live, in-scope boxes from fleet.md. IPs avoid stale LAN DNS on war.
FLEET = {
    "archlinux": "100.91.183.24",
    "war": "100.79.164.88",
    "blaises-mini": "100.67.231.41",
}

# name: (provider instance, model, effort option)
MODELS = {
    "opus": ("claudeAgent", "claude-opus-5-5", "effort"),
    "sol": ("codex", "gpt-6.1-sol", "reasoningEffort"),
}
# Opus and Sol may start either model, including their own.
# max and everything above it are never used.
EFFORTS = ("low", "medium", "high", "xhigh")
# V2 run statuses that end a run; "error" is a provider session failure.
TERMINAL = ("completed", "interrupted", "failed", "cancelled", "rolled_back", "error")
VERSION = "0.1.0"
PORT = 3773
STATE_DIR = Path.home() / ".local/state/t3-fleet-agent"


def local_cli():
    runtime = Path.home() / ".t3/runtime"
    state = runtime / "service-state.json"
    if state.exists():
        version = json.loads(state.read_text())["activeVersion"]
    else:
        # Desktop app: use its installed version, not an unrelated npm release.
        import plistlib
        # 0.1.0 renamed the bundle from (Alpha) to (Beta).
        bundles = [root / ("T3 Code (%s).app" % channel) for channel in ("Beta", "Alpha")
                   for root in (Path("/Applications"), Path.home() / "Applications")]
        bundle = next((p for p in bundles if p.exists()), None)
        if bundle is None:
            raise RuntimeError("Cannot locate the T3 desktop app or service state")
        with (bundle / "Contents/Info.plist").open("rb") as f:
            version = plistlib.load(f)["CFBundleShortVersionString"]
    cli = runtime / "versions" / version / "t3"
    if not cli.is_file():
        raise RuntimeError("The running version's T3 executable is missing")
    if version != VERSION:
        raise RuntimeError("This helper supports T3 %s; recheck the API before using another version" % VERSION)
    return str(cli)


def model_name(selection):
    """Map a thread's model selection to a MODELS name, or None."""
    model = selection.get("model", "")
    if model.startswith("claude-opus-"):
        return "opus"
    if model.startswith("gpt-") and model.endswith("-sol"):
        return "sol"
    return next((name for name, spec in MODELS.items() if spec[1] == model), None)


def caller():
    """Return (T3 thread ID, model selection) of the agent running this, or None.

    None means no agent: a person at a shell. An agent whose T3 thread can't be
    found raises, so the rules can't be skipped by accident.
    """
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
    if not session:
        return None
    # V2 records each provider's native session in its provider thread; read-only.
    db = Path.home() / ".t3/userdata/statev2.sqlite"
    try:
        with sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5) as conn:
            row = conn.execute(
                "SELECT t.thread_id, json_extract(t.payload_json, '$.modelSelection')"
                " FROM orchestration_v2_projection_provider_threads p"
                " JOIN orchestration_v2_projection_threads t ON t.thread_id = p.thread_id"
                " WHERE instr(p.payload_json, ?) > 0 AND t.deleted_at IS NULL"
                " ORDER BY p.updated_at DESC", (session,)).fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Cannot read this box's T3 state to identify the caller: %s" % error) from None
    if row is None:
        raise RuntimeError("Delegate from a T3 thread; this agent session isn't one")
    return row[0], json.loads(row[1])


def summarize(projection):
    """State plus the child's final answer, which is its report. Never the transcript."""
    thread = projection["thread"]
    runs = sorted(projection.get("runs", []), key=lambda run: run["ordinal"])
    state = runs[-1]["status"] if runs else "pending"
    sessions = sorted(projection.get("providerSessions", []), key=lambda s: s["updatedAt"])
    session = sessions[-1] if sessions else {}
    if session.get("status") == "error" and state not in TERMINAL:
        state = "error"
    answers = [m["text"] for m in projection.get("messages", [])
               if m.get("role") == "assistant" and m.get("text") and not m.get("streaming")]
    return {
        "threadId": thread["id"],
        "title": thread["title"],
        "modelSelection": thread["modelSelection"],
        "worktreePath": thread.get("worktreePath"),
        "state": state,
        "lastError": session.get("lastError"),
        "report": answers[-1] if answers and state in TERMINAL else None,
    }


class Rpc:
    """Minimal WebSocket client for T3's Effect RPC endpoint (JSON frames).

    0.1.0 removed HTTP dispatch; commands go over /ws like the web client's.
    """

    def __init__(self, token):
        self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET /ws?orchestrationProtocol=2 HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                           "Sec-WebSocket-Version: 13\r\nAuthorization: Bearer %s\r\n\r\n"
                           % (PORT, key, token)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("T3 closed the WebSocket during the handshake")
            head += chunk
        head, self.buffer = head.split(b"\r\n\r\n", 1)
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not head.startswith(b"HTTP/1.1 101") or accept not in head:
            raise RuntimeError("T3 refused the WebSocket: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.next_id = 0

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("T3 closed the WebSocket")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _send(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        header = bytes([0x80 | opcode])
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            header += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _message(self):
        parts = []
        while True:
            first, second = self._read(2)
            n = second & 0x7F
            if n == 126:
                n = int.from_bytes(self._read(2), "big")
            elif n == 127:
                n = int.from_bytes(self._read(8), "big")
            payload = self._read(n)
            opcode = first & 0x0F
            if opcode == 8:
                raise RuntimeError("T3 closed the WebSocket")
            if opcode == 9:
                self._send(10, payload)
            elif opcode in (0, 1, 2):
                parts.append(payload)
                if first & 0x80:
                    return json.loads(b"".join(parts))

    def call(self, tag, payload):
        self.next_id += 1
        request_id = str(self.next_id)
        self._send(1, json.dumps({"_tag": "Request", "id": request_id, "tag": tag,
                                  "payload": payload, "headers": []}).encode())
        while True:
            message = self._message()
            for item in message if isinstance(message, list) else [message]:
                if item.get("_tag") == "Ping":
                    self._send(1, b'{"_tag":"Pong"}')
                elif item.get("_tag") == "Defect":
                    raise RuntimeError("T3 RPC defect: %s" % json.dumps(item.get("defect"))[:2000])
                elif item.get("_tag") == "Exit" and str(item.get("requestId")) == request_id:
                    exit = item["exit"]
                    if exit.get("_tag") == "Success":
                        return exit.get("value")
                    raise RuntimeError("T3 %s failed: %s" % (tag, json.dumps(exit.get("cause"))[:2000]))

    def close(self):
        try:
            self._send(8, b"")
        finally:
            self.sock.close()


def worker(request):
    cli = local_cli()
    env = os.environ.copy()
    env.pop("T3_SERVICE_LAUNCHER_CONTEXT", None)
    issued = subprocess.run([cli, "auth", "session", "issue", "--ttl", "2m", "--label", "t3-fleet-agent", "--json"],
                            env=env, capture_output=True, text=True, timeout=15)
    if issued.returncode:
        raise RuntimeError("T3 credential issuance failed; credential output withheld")
    auth = json.loads(issued.stdout)
    token = auth["token"]

    rpc = None

    def api(path):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                     headers={"Authorization": "Bearer " + token, "x-t3-orchestration-protocol": "2"})
        try:
            # Keep a local credential local, even when a box exports HTTP_PROXY.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace").replace(token, "[REDACTED]")
            raise RuntimeError("T3 HTTP %s: %s" % (error.code, detail[:2000])) from None

    def rpc_call(tag, payload):
        nonlocal rpc
        if rpc is None:
            rpc = Rpc(token)
        try:
            return rpc.call(tag, payload)
        except RuntimeError as error:
            raise RuntimeError(str(error).replace(token, "[REDACTED]")) from None

    def dispatch(command):
        return rpc_call("orchestration.dispatchCommand", command)

    def read(thread_id):
        return api("/api/orchestration/threads/" + thread_id)["projection"]

    def send(thread_id, text):
        dispatch({"type": "message.dispatch", "createdBy": "agent", "creationSource": "server", "commandId": str(uuid.uuid4()), "threadId": thread_id,
                  "messageId": str(uuid.uuid4()), "text": text, "attachments": [],
                  "deliveryIntent": "auto", "dispatchMode": {"type": "queue_after_active"}})

    try:
        action = request["action"]
        if action == "projects":
            snapshot = api("/api/orchestration/shell")
            return {"projects": [{k: p.get(k) for k in ("id", "title", "workspaceRoot")} for p in snapshot["projects"]]}
        if action == "start":
            root = Path(request["cwd"]).expanduser().resolve()
            if not root.is_dir():
                raise RuntimeError("Workspace does not exist on the target: " + str(root))
            projects = api("/api/orchestration/shell")["projects"]
            project = next((p for p in projects if p["workspaceRoot"] == str(root) and not p.get("deletedAt")), None)
            if project is None:
                raise RuntimeError("Add this workspace as a T3 project on the target first")
            worktree = request.get("worktree")
            if worktree:
                worktree = str(Path(worktree).expanduser().resolve())
                registered = subprocess.run(["git", "-C", str(root), "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=10)
                if registered.returncode or "worktree " + worktree not in registered.stdout.splitlines():
                    raise RuntimeError("--worktree must be an existing git worktree of the target project")
            branch_result = subprocess.run(["git", "-C", worktree or str(root), "symbolic-ref", "--short", "HEAD"],
                                           capture_output=True, text=True, timeout=10)
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
            strategy = {"type": "existing_worktree", "worktreePath": worktree} if worktree else {"type": "root"}
            if branch:
                strategy["branch"] = branch
            selection = request["selection"]
            namespace = uuid.uuid5(uuid.NAMESPACE_URL, "t3-fleet-agent:" + request["requestId"])
            thread_id = str(uuid.uuid5(namespace, "thread"))
            # T3 keeps a receipt per launch command ID, so a retried launch replays, not duplicates.
            launched = rpc_call("orchestration.launchThread", {
                "commandId": str(uuid.uuid5(namespace, "launch")), "creationSource": "server",
                "threadId": thread_id, "projectId": project["id"], "title": request["title"],
                "modelSelection": selection, "runtimeMode": request["runtimeMode"],
                "interactionMode": request["interactionMode"], "workspaceStrategy": strategy,
                "initialMessage": {"messageId": str(uuid.uuid5(namespace, "message")),
                                   "text": request["prompt"], "attachments": []}})
            thread = launched["projection"]["thread"]
            if (thread["projectId"] != project["id"] or thread["modelSelection"] != selection
                    or thread["runtimeMode"] != request["runtimeMode"]
                    or thread["interactionMode"] != request["interactionMode"]):
                raise RuntimeError("Request ID already belongs to a thread with different settings")
        else:
            thread_id = request["threadId"]
            if action == "send":
                send(thread_id, request["prompt"])
            elif action == "interrupt":
                runs = [run for run in read(thread_id)["runs"] if run["status"] not in TERMINAL]
                for run in runs:
                    dispatch({"type": "run.interrupt", "commandId": str(uuid.uuid4()),
                              "threadId": thread_id, "runId": run["id"]})
            elif action in ("archive", "unarchive"):
                dispatch({"type": "thread." + action, "commandId": str(uuid.uuid4()), "threadId": thread_id})
                if action == "archive":
                    # Archived threads are hidden from the detail endpoint.
                    return {"threadId": thread_id, "archived": True}
        deadline = time.monotonic() + request.get("wait", 0)
        while True:
            result = summarize(read(thread_id))
            if result["state"] in TERMINAL or time.monotonic() >= deadline:
                result["waitTimedOut"] = request.get("wait", 0) > 0 and result["state"] not in TERMINAL
                return result
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    finally:
        if rpc is not None:
            rpc.close()
        revoked = subprocess.run([cli, "auth", "session", "revoke", auth["sessionId"]], env=env,
                                 capture_output=True, text=True, timeout=15)
        if revoked.returncode:
            print("Temporary session revocation failed; it expires after two minutes", file=sys.stderr)


def call(machine, request):
    """Run a worker request on machine: in-process if local, else over SSH."""
    if socket.gethostname().lower().split(".")[0] == machine:
        return worker(request)
    fqdn = machine + ".tail2b35ba.ts.net"
    source = base64.b64encode(Path(__file__).read_bytes()).decode()
    code = "import base64,sys;sys.argv=['t3-fleet-agent','--worker'];exec(base64.b64decode(" + repr(source) + "))"
    process = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                              "-o", "HostName=" + FLEET[machine], "-o", "HostKeyAlias=" + fqdn,
                              "blaise@" + fqdn, "python3 -c " + shlex.quote(code)],
                             input=json.dumps(request), text=True, capture_output=True, timeout=100)
    if process.stderr:
        print(process.stderr.strip(), file=sys.stderr)
    if process.returncode:
        try:
            remote_error = json.loads(process.stdout).get("error")
        except (ValueError, AttributeError):
            remote_error = None
        raise RuntimeError(remote_error or "Target unreachable or remote helper failed")
    return json.loads(process.stdout)


def watch(machine, thread_id, parent):
    """Wait for a child to finish, then post the outcome into its parent's thread.

    Gives up after a day, or after half an hour of the child's box being
    unreachable, and says so in the parent's thread either way.
    """
    lock = STATE_DIR / ("watch-%s.lock" % thread_id)
    give_up = time.monotonic() + 24 * 3600
    unreachable_since = None
    result = {"state": "still running after a day", "title": thread_id}
    try:
        while time.monotonic() < give_up:
            try:
                result = call(machine, {"action": "wait", "threadId": thread_id, "wait": 50})
                unreachable_since = None
            except Exception as error:
                unreachable_since = unreachable_since or time.monotonic()
                if time.monotonic() - unreachable_since > 1800:
                    result = {"state": "unreachable", "title": thread_id, "lastError": str(error)}
                    break
                time.sleep(60)
                continue
            if result["state"] in TERMINAL:
                break
        text = ("[t3-fleet] %r on %s, thread %s: %s."
                % (result.get("title"), machine, thread_id, result["state"]))
        if result.get("lastError"):
            text += "\nError: " + str(result["lastError"])[:500]
        if result.get("report"):
            text += "\n\n" + result["report"]
        local = socket.gethostname().lower().split(".")[0]
        call(local, {"action": "send", "threadId": parent, "prompt": text})
    finally:
        lock.unlink(missing_ok=True)
        log = STATE_DIR / ("watch-%s.log" % thread_id)
        if log.exists() and log.stat().st_size == 0:
            log.unlink()


def spawn_watcher(machine, thread_id, parent):
    """Start one detached watcher per child; a retried launch reuses it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(STATE_DIR / ("watch-%s.lock" % thread_id), os.O_CREAT | os.O_EXCL))
    except FileExistsError:
        return
    command = [sys.executable, str(Path(__file__).resolve()), machine, "watch", thread_id, "--parent", parent]
    if sys.platform.startswith("linux"):
        # Leave T3's service cgroup, so a T3 restart doesn't kill the watcher.
        command = ["systemd-run", "--user", "--quiet", "--collect", "--unit", "t3-fleet-watch-" + thread_id] + command
    log = (STATE_DIR / ("watch-%s.log" % thread_id)).open("a")
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def main():
    if sys.argv[1:] == ["--worker"]:
        try:
            print(json.dumps(worker(json.load(sys.stdin))))
        except Exception as error:
            print(json.dumps({"error": str(error)}))
            return 1
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine", choices=FLEET)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("projects", help="List the box's T3 projects")
    start = commands.add_parser("start", help="Create a visible T3 thread; read its prompt from stdin")
    start.add_argument("--cwd", required=True, help="Existing project directory on the TARGET box")
    start.add_argument("--model", required=True, choices=MODELS)
    start.add_argument("--effort", required=True, choices=EFFORTS,
                       help="Effort you judge the task needs; max is never used")
    start.add_argument("--plan", action="store_true", help="Start the child in plan mode")
    start.add_argument("--title", required=True)
    start.add_argument("--worktree", help="Existing git worktree on the target; otherwise uses the project checkout")
    start.add_argument("--request-id", help="Reuse this ID to retry the same launch without duplicating work")
    start.add_argument("--wait", type=int, choices=range(0, 51), metavar="0..50", default=0)
    for action in ("read", "wait", "send", "interrupt", "archive", "unarchive", "watch"):
        command = commands.add_parser(action)
        command.add_argument("thread_id", type=lambda value: str(uuid.UUID(value)))
        if action == "wait":
            command.add_argument("--wait", type=int, choices=range(1, 51), metavar="1..50", default=50)
        if action == "watch":
            command.add_argument("--parent", required=True)
    args = parser.parse_args()

    if args.action == "watch":
        watch(args.machine, args.thread_id, args.parent)
        return 0

    request = {"action": args.action, "wait": getattr(args, "wait", 0)}
    parent = None
    if args.action == "start":
        found = caller()
        effort = args.effort
        if found is not None:
            parent, selection = found
            if model_name(selection) not in ("opus", "sol"):
                parser.error("only Opus and Sol delegate; do this task yourself")
        prompt = sys.stdin.read().strip()
        if not prompt:
            parser.error("Provide a nonempty task prompt on stdin")
        provider, model, option = MODELS[args.model]
        request.update(cwd=args.cwd, selection={"instanceId": provider, "model": model,
                                                "options": [{"id": option, "value": effort}]},
                       runtimeMode="full-access", interactionMode="plan" if args.plan else "default",
                       title=args.title, prompt=prompt, worktree=args.worktree,
                       requestId=args.request_id or str(uuid.uuid4()))
        print(json.dumps({"machine": args.machine, "requestId": request["requestId"], "effort": effort}),
              file=sys.stderr, flush=True)
    elif args.action == "send":
        request["threadId"] = args.thread_id
        request["prompt"] = sys.stdin.read().strip()
        if not request["prompt"]:
            parser.error("Provide a nonempty message on stdin")
    elif args.action != "projects":
        request["threadId"] = args.thread_id

    result = call(args.machine, request)
    if args.action == "start" and parent is not None and result.get("state") not in TERMINAL:
        spawn_watcher(args.machine, result["threadId"], parent)
        result["parentNotified"] = "when it finishes"
    result["machine"] = args.machine
    print(json.dumps(result, indent=2))
    return 1 if result.get("state") == "error" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(1)
