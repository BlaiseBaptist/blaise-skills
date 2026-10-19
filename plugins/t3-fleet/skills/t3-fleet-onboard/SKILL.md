---
name: t3-fleet-onboard
description: "Use for T3 fleet onboarding, repair, or `t3` commands."
---

# t3-fleet-onboard

Onboard, re-check, or repair one fleet box, `$H`, over SSH from another box.
Every step is safe to re-run; on a healthy box the whole skill is a health
check. `SKILL_DIR` is this skill's directory. The roster and per-box facts
(paths, quirks, which box is dormant) are in `fleet.md` in
`T3_code_improvements`; read it first when you have it.

Run every remote command as `ssh -o BatchMode=yes blaise@$H '...'`. Find out
the box shape first with `uname -s`, because the steps differ:

| | Linux (`archlinux`, `war`, `bigarch`, `littlearch`) | Mac (`blaises-mini`, `blaises-macbook-air`) |
|---|---|---|
| T3 | CLI service `t3code.service` (systemd user unit) | desktop app `T3 Code (Beta).app`, updates itself |
| `t3` CLI | `npx t3@<version>` | none on `PATH`; use the app's UI |
| Serve mount | `T3CODE_TAILSCALE_SERVE=true` drop-in | `tailscale serve` by hand |
| Skills sync | systemd user timer | LaunchAgent |

Don't install a service on a Mac or reach for `systemctl` there.

## Preflight

1. **Ownership.** Only the six boxes above. `nuc`, `teddy-computer`,
   `lovelandnuc`, and `m1airlinux` are shared or out of scope: never install
   on them, even if SSH reaches them.
2. **Reachability.** `$H` should appear in `tailscale status`. The real test
   is `ssh -o BatchMode=yes blaise@$H true`. If SSH fails, stop and tell the
   user. Don't fall back to a password or another username.
3. **Names.** `war` resolves some fleet names to stale LAN addresses. If SSH
   works but HTTPS hangs, compare `getent hosts $H.tail2b35ba.ts.net` with
   `tailscale status` and dial the `100.x` address.

**Mac that refuses SSH:** macOS Remote Login is off. Only the user can fix
that at the keyboard: System Settings > General > Sharing > Remote Login,
then append `war`'s and `archlinux`'s `~/.ssh/id_ed25519.pub` to the Mac's
`~/.ssh/authorized_keys`. Tailscale SSH doesn't replace it: on a Mac,
`tailscale set --ssh` succeeds but nothing listens.

**Linux Tailscale SSH**, as a backstop if keys break: `tailscale set --ssh`
on the box, then prove it from another box with
`tailscale ssh blaise@$H hostname`. It needs `OperatorUser` set to `blaise`
and an `ssh` rule in the tailnet ACL. If it fails for either reason, hand it
to the user.

## Install

**1. Node 24, user-local** (needed on both shapes; Macs ship no `node`):

```sh
ssh -o BatchMode=yes blaise@$H '
  set -e
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) P=linux-x64 ;; Linux-aarch64) P=linux-arm64 ;;
    Darwin-arm64) P=darwin-arm64 ;; Darwin-x86_64) P=darwin-x64 ;;
    *) echo "unknown platform" >&2; exit 1 ;;
  esac
  test -x ~/.local/share/t3-node/bin/node || {
    mkdir -p ~/.local/share/t3-node
    curl -fsSL "https://nodejs.org/dist/v24.19.0/node-v24.19.0-$P.tar.xz" \
      | tar -xJ --strip-components=1 -C ~/.local/share/t3-node; }
  ~/.local/share/t3-node/bin/node --version'
```

**2. T3.** On Linux:

```sh
ssh -o BatchMode=yes blaise@$H '
  export PATH="$HOME/.local/share/t3-node/bin:$PATH"
  env -u T3_SERVICE_LAUNCHER_CONTEXT npx -y t3@latest service install'
```

The CLI you run must match the version the box's service runs, or it fails
with `The service launcher started a different t3 version`. For a box held
at a version, use the version in `~/.t3/runtime/versions/`. Back up
`~/.t3/userdata/statev2.sqlite` before an upgrade. On a Mac, only check that
the app is up; if it isn't, ask the user to launch it.

**3. Serve the web UI** at `https://$H.tail2b35ba.ts.net/`. On Linux, write
the drop-in (`systemctl --user edit` hangs under BatchMode):

```sh
ssh -o BatchMode=yes blaise@$H '
  mkdir -p ~/.config/systemd/user/t3code.service.d
  printf "[Service]\nEnvironment=T3CODE_TAILSCALE_SERVE=true\n" \
    > ~/.config/systemd/user/t3code.service.d/override.conf
  systemctl --user daemon-reload && systemctl --user restart t3code.service
  loginctl enable-linger blaise'
```

On a Mac, run `tailscale serve --bg --set-path=/ http://127.0.0.1:3773`. Also
pin the name with `tailscale set --hostname=$H` if `tailscale debug prefs`
shows an empty `Hostname`. An unpinned Mac renames itself after a
`tailscaled` restart, and serve keeps the old name.

**4. Providers.** An installed CLI isn't enough; it must be signed in. The
`pong` check under Verify is the proof. Fix it with `ssh -t blaise@$H claude`
and `/login`, unless `fleet.md` says the box uses a token or the proxy.

## Skills

Use the HTTPS URL, because fleet boxes have no GitHub SSH key:

```sh
ssh -o BatchMode=yes blaise@$H '
  set -e; export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
  claude plugin marketplace add https://github.com/BlaiseBaptist/blaise-skills.git
  claude plugin install t3-fleet@blaise-skills --scope user'
```

Every box gets `t3-fleet`. Only desktop boxes get `desktop@blaise-skills`.
The hourly sync then updates Claude and Codex and installs Codex's copy
itself. Install the sync script and its timer:

```sh
S="$SKILL_DIR/scripts"
ssh -o BatchMode=yes blaise@$H 'mkdir -p ~/.local/bin && cat > ~/.local/bin/claude-skills-sync && chmod +x ~/.local/bin/claude-skills-sync' < "$S/claude-skills-sync.sh"
# Linux
cat "$S/claude-skills-sync.service" | ssh -o BatchMode=yes blaise@$H 'mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/claude-skills-sync.service'
cat "$S/claude-skills-sync.timer"   | ssh -o BatchMode=yes blaise@$H 'cat > ~/.config/systemd/user/claude-skills-sync.timer'
ssh -o BatchMode=yes blaise@$H 'systemctl --user daemon-reload && systemctl --user enable --now claude-skills-sync.timer'
# Mac
sed "s|HOME_DIR|/Users/blaise|g" "$S/com.blaise.claude-skills-sync.plist" | ssh -o BatchMode=yes blaise@$H '
  P=~/Library/LaunchAgents/com.blaise.claude-skills-sync.plist; mkdir -p ~/Library/LaunchAgents; cat > $P
  launchctl bootout gui/$(id -u)/com.blaise.claude-skills-sync 2>/dev/null || true
  launchctl bootstrap gui/$(id -u) $P'
```

Judge a run by its log (`journalctl --user -u claude-skills-sync` or
`~/Library/Logs/claude-skills-sync.log`), not the exit code. Updates apply
only to sessions started afterwards.

## Verify

All three must pass:

1. **T3 up.** On Linux, `systemctl --user is-active t3code.service` returns
   `active`. On a Mac, `curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:3773/`
   returns `200`.
2. **Served.** From another box, `curl -fsS -o /dev/null -w '%{http_code}' https://$H.tail2b35ba.ts.net/`
   returns `200`. Check from `archlinux` rather than `war` (stale DNS).
3. **Signed in.** `claude -p "Reply with exactly: pong"` prints `pong`.
   Read the output, because it exits 0 even when auth has expired. On Linux,
   wrap it in `timeout 90`. Macs have no `timeout`, so bound it with
   `-o ConnectTimeout=10` from your side, and export
   `PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH` first.

Then make sure the box has a T3 project for its workspace. Add it in the web
UI if it's missing.

## Pairing and Connect

To pair a browser or phone over the tailnet on Linux, run
`env -u T3_SERVICE_LAUNCHER_CONTEXT npx -y t3@<version> pair --tailscale`.
It prints a `/pair#token=` URL that expires in 5 minutes, so mint it right
before use. On a Mac, pair from the app. T3 Connect (`t3 connect`, the relay)
is a different mechanism. The fleet uses it, so don't link, unlink, or relink
it during onboarding.

## Traps

- **`T3_SERVICE_LAUNCHER_CONTEXT`.** A session hosted by T3 inherits it, and
  every `t3` CLI call then fails with `ipc-unavailable`. Always run
  `env -u T3_SERVICE_LAUNCHER_CONTEXT`.
- **Mac `PATH` over SSH.** It isn't a login shell, so `claude`, `tailscale`,
  and `brew` look missing. Export `~/.local/bin:/opt/homebrew/bin` in every
  remote command.
- **Versions.** There's no fleet-wide pin, and boxes may differ, but a 0.0.x
  (V1) box can't talk to a 0.1.x (V2) one. Pinning one box means installing
  an exact `t3@<version>`. Nothing re-pins it later.
