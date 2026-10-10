#!/usr/bin/env python3
"""Bring blaise-skills plugins up to date in Claude Code and in Codex.

~/.local/bin/claude-skills-sync refreshes each harness's copy of the
marketplace, then runs this. Each harness installs the same skills from GitHub
through its own plugin system, so a failure in one never stops the other.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MARKETPLACE = "blaise-skills"
SOURCE = "https://github.com/BlaiseBaptist/claude-skills.git"


def output(command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def update_claude():
    """Update installed plugins and return their names."""
    names = []
    for plugin in json.loads(output(["claude", "plugin", "list", "--json"])):
        if plugin["id"].endswith("@" + MARKETPLACE):
            # No --yes: older Claude versions reject it for these git sources.
            subprocess.run(["claude", "plugin", "update", plugin["id"]], check=True)
            names.append(plugin["id"].split("@")[0])
    return names


def update_codex(bootstrap):
    """Reinstall Codex's plugins from its refreshed marketplace snapshot.

    Plugins without a manifest version install as "local", so a marketplace
    upgrade alone leaves the installed copy stale. A box with none yet gets the
    plugins Claude has, or t3-fleet.
    """
    installed = json.loads(output(["codex", "plugin", "list", "--json"]))["installed"]
    names = [p["name"] for p in installed if p["marketplaceName"] == MARKETPLACE] or bootstrap or ["t3-fleet"]
    for name in names:
        subprocess.run(["codex", "plugin", "add", name + "@" + MARKETPLACE], check=True)
    return names


def retire_links(home):
    """Remove the ~/.agents/skills links the old sync made for Codex.

    Only links still pointing where that sync left them; never a user's own.
    """
    state = home / ".local/state/blaise-skills/shared-links.json"
    if not state.exists():
        return
    for name, target in json.loads(state.read_text()).items():
        link = home / ".agents/skills" / name
        if link.is_symlink() and os.readlink(link) == target:
            link.unlink()
    state.unlink()


def install_runner(home):
    """Keep the timer's stable entrypoint current with this version."""
    source = Path(__file__).with_name("claude-skills-sync.sh")
    destination = home / ".local/bin/claude-skills-sync"
    if destination.exists() and destination.read_bytes() == source.read_bytes():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement leaves an already-running shell's file intact.
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as f:
        f.write(source.read_bytes())
    os.chmod(f.name, 0o755)
    os.replace(f.name, destination)


def main():
    home = Path.home()
    failed = False
    claude_names = []
    if shutil.which("claude"):
        try:
            claude_names = update_claude()
        except subprocess.CalledProcessError as error:
            print("Claude plugin update failed: %s" % error, file=sys.stderr)
            failed = True
    codex_ok = True
    if shutil.which("codex"):
        try:
            print("Codex plugins: " + ", ".join(update_codex(claude_names)))
        except (subprocess.CalledProcessError, KeyError, ValueError) as error:
            print("Codex plugin update failed: %s" % error, file=sys.stderr)
            failed = True
            codex_ok = False
    if codex_ok:
        retire_links(home)
    install_runner(home)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
