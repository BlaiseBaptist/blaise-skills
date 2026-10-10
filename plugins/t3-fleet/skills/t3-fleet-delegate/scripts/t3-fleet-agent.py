#!/usr/bin/env python3
"""Control real T3 threads via fleet SSH and T3 0.0.45's local HTTP API.

Enforces the fleet's delegation rules: only Opus and Sol delegate, effort is
one level below what they ask for, and max effort is never used. When the
child finishes, its parent's T3 thread gets a message.

No third-party dependencies, stored credentials, or T3 source changes.
"""

import argparse
import base64
import datetime
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
    "sonnet": ("claudeAgent", "claude-sonnet-5-5", "effort"),
    "luna": ("codex", "gpt-6-luna", "reasoningEffort"),
    "haiku": ("claudeAgent", "claude-haiku-5-5", "effort"),
}
# max and everything above it are never used.
EFFORTS = ("low", "medium", "high", "xhigh")
TERMINAL = ("completed", "interrupted", "error")
STATE_DIR = Path.home() / ".local/state/t3-fleet-agent"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def local_cli():
    runtime = Path.home() / ".t3/runtime"
    state = runtime / "service-state.json"
    if state.exists():
        version = json.loads(state.read_text())["activeVersion"]
    else:
        # Desktop app: use its installed version, not an unrelated npm release.
        import plistlib
        bundles = [Path("/Applications/T3 Code (Alpha).app"), Path.home() / "Applications/T3 Code (Alpha).app"]
        bundle = next((p for p in bundles if p.exists()), None)
        if bundle is None:
            raise RuntimeError("Cannot locate the T3 desktop app or service state")
        with (bundle / "Contents/Info.plist").open("rb") as f:
            version = plistlib.load(f)["CFBundleShortVersionString"]
    cli = runtime / "versions" / version / "t3"
    if not cli.is_file():
        raise RuntimeError("The running version's T3 executable is missing")
    if version != "0.0.45":
        raise RuntimeError("This helper supports T3 0.0.45; recheck the API before using another version")
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
    # T3 records each provider session in its resume cursor; read-only.
    db = Path.home() / ".t3/userdata/state.sqlite"
    try:
        with sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5) as conn:
            row = conn.execute(
                "SELECT t.thread_id, t.model_selection_json FROM provider_session_runtime r"
                " JOIN projection_threads t ON t.thread_id = r.thread_id"
                " WHERE instr(r.resume_cursor_json, ?) > 0", (session,)).fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Cannot read this box's T3 state to identify the caller: %s" % error) from None
    if row is None:
        raise RuntimeError("Delegate from a T3 thread; this agent session isn't one")
    return row[0], json.loads(row[1])


def summarize(thread, full=False):
    turn = thread.get("latestTurn") or {}
    session = thread.get("session") or {}
    state = turn.get("state", "pending")
    if session.get("status") == "error":
        state = "error"
    messages = [{k: m.get(k) for k in ("id", "role", "text")} for m in thread.get("messages", [])]
    result = {
        "threadId": thread["id"],
        "title": thread["title"],
        "modelSelection": thread["modelSelection"],
        "runtimeMode": thread["runtimeMode"],
        "worktreePath": thread.get("worktreePath"),
        "state": state,
        "sessionStatus": session.get("status"),
        "lastError": session.get("lastError"),
    }
    if full:
        result["messages"] = messages
    else:
        answers = [m["text"] for m in messages if m["role"] == "assistant" and m.get("text")]
        result["answer"] = answers[-1] if answers else None
    return result


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

    def api(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request("http://127.0.0.1:3773" + path, data=data,
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            # Keep a local credential local, even when a box exports HTTP_PROXY.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace").replace(token, "[REDACTED]")
            raise RuntimeError("T3 HTTP %s: %s" % (error.code, detail[:2000])) from None

    def dispatch(payload):
        return api("/api/orchestration/dispatch", payload)

    def read(thread_id):
        return api("/api/orchestration/threads/" + thread_id)["thread"]

    def send(thread, message_id, text, command_id):
        dispatch({"type": "thread.turn.start", "commandId": command_id, "threadId": thread["id"],
                  "message": {"messageId": message_id, "role": "user", "text": text, "attachments": []},
                  "modelSelection": thread["modelSelection"], "runtimeMode": thread["runtimeMode"],
                  "interactionMode": thread["interactionMode"], "createdAt": now()})

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
            selection = request["selection"]
            namespace = uuid.uuid5(uuid.NAMESPACE_URL, "t3-fleet-agent:" + request["requestId"])
            thread_id = str(uuid.uuid5(namespace, "thread"))
            message_id = str(uuid.uuid5(namespace, "message"))
            try:
                thread = read(thread_id)
            except RuntimeError as error:
                if "T3 HTTP 404:" not in str(error):
                    raise
                thread = None
            if thread is None:
                dispatch({"type": "thread.create", "commandId": str(uuid.uuid5(namespace, "create")),
                          "threadId": thread_id, "projectId": project["id"], "title": request["title"],
                          "modelSelection": selection, "runtimeMode": request["runtimeMode"],
                          "interactionMode": request["interactionMode"], "branch": branch,
                          "worktreePath": worktree, "createdAt": now()})
                thread = read(thread_id)
            elif (thread["projectId"] != project["id"] or thread["modelSelection"] != selection
                  or thread.get("worktreePath") != worktree or thread["runtimeMode"] != request["runtimeMode"]
                  or thread["interactionMode"] != request["interactionMode"]):
                raise RuntimeError("Request ID already belongs to a thread with different settings")
            existing = next((m for m in thread.get("messages", []) if m["id"] == message_id), None)
            if existing and existing.get("text") != request["prompt"]:
                raise RuntimeError("Request ID already belongs to a different prompt")
            if not existing:
                send(thread, message_id, request["prompt"], str(uuid.uuid5(namespace, "start")))
        else:
            thread_id = request["threadId"]
            if action == "send":
                send(read(thread_id), str(uuid.uuid4()), request["prompt"], str(uuid.uuid4()))
            elif action in ("interrupt", "archive", "unarchive"):
                command = {"type": "thread.turn.interrupt" if action == "interrupt" else "thread." + action,
                           "commandId": str(uuid.uuid4()), "threadId": thread_id}
                if action == "interrupt":
                    command["createdAt"] = now()
                dispatch(command)
                if action == "archive":
                    # Archived threads are hidden from the detail endpoint.
                    return {"threadId": thread_id, "archived": True}
        deadline = time.monotonic() + request.get("wait", 0)
        while True:
            result = summarize(read(thread_id), request.get("full", False))
            if result["state"] in TERMINAL or time.monotonic() >= deadline:
                result["waitTimedOut"] = request.get("wait", 0) > 0 and result["state"] not in TERMINAL
                return result
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    finally:
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
        text = ("[t3-fleet] Delegated thread %r on %s: %s.\nRead it with the delegate helper: %s read %s"
                % (result.get("title"), machine, result["state"], machine, thread_id))
        if result.get("lastError"):
            text += "\nError: " + str(result["lastError"])[:500]
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
                       help="Effort you judge the task needs; Opus and Sol callers get one level less")
    start.add_argument("--plan", action="store_true", help="Start the child in plan mode")
    start.add_argument("--title", required=True)
    start.add_argument("--worktree", help="Existing git worktree on the target; otherwise uses the project checkout")
    start.add_argument("--request-id", help="Reuse this ID to retry the same launch without duplicating work")
    start.add_argument("--wait", type=int, choices=range(0, 51), metavar="0..50", default=0)
    for action in ("read", "wait", "send", "interrupt", "archive", "unarchive", "watch"):
        command = commands.add_parser(action)
        command.add_argument("thread_id", type=lambda value: str(uuid.UUID(value)))
        if action in ("read", "wait"):
            command.add_argument("--full", action="store_true", help="Include every message, not just the final answer")
        if action == "wait":
            command.add_argument("--wait", type=int, choices=range(1, 51), metavar="1..50", default=50)
        if action == "watch":
            command.add_argument("--parent", required=True)
    args = parser.parse_args()

    if args.action == "watch":
        watch(args.machine, args.thread_id, args.parent)
        return 0

    request = {"action": args.action, "wait": getattr(args, "wait", 0), "full": getattr(args, "full", False)}
    parent = None
    if args.action == "start":
        found = caller()
        effort = args.effort
        if found is not None:
            parent, selection = found
            if model_name(selection) not in ("opus", "sol"):
                parser.error("only Opus and Sol delegate; do this task yourself")
            # Opus and Sol overestimate what a child needs: take one level off.
            effort = EFFORTS[max(0, EFFORTS.index(effort) - 1)]
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
