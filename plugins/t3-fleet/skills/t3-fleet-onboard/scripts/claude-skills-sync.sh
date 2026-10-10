#!/bin/sh
# Pull blaise-skills into Claude Code and Codex. Each harness installs the same
# skills from GitHub through its own plugin system; a failure in one doesn't
# stop the other. Lives outside both plugin caches because those move on every
# update, so a unit pointing into one would break the first time it worked.
#
# systemd hands a unit PATH=/usr/local/bin:/usr/bin, and launchd on macOS is
# no better. claude and codex may be under ~/.local/bin (npm install, the Air)
# or under /opt/homebrew/bin (cask, blaises-mini), and some boxes (littlearch,
# both Macs) have no system node at all, only the Node 24 that onboarding step 1
# installs. Reach for all three; the missing ones cost nothing.
export PATH="$HOME/.local/bin:$HOME/.local/share/t3-node/bin:/opt/homebrew/bin:$PATH"

source=https://github.com/BlaiseBaptist/claude-skills.git
status=0
root=

if command -v claude >/dev/null 2>&1; then
  if claude plugin marketplace update blaise-skills; then
    root="$HOME/.claude/plugins/marketplaces/blaise-skills"
  else
    status=1
  fi
fi

if command -v codex >/dev/null 2>&1; then
  codex plugin marketplace list --json | grep -q '"name": "blaise-skills"' \
    || codex plugin marketplace add "$source" || status=1
  if codex plugin marketplace upgrade blaise-skills; then
    [ -n "$root" ] || root="${CODEX_HOME:-$HOME/.codex}/.tmp/marketplaces/blaise-skills"
  else
    status=1
  fi
fi

if [ -z "$root" ]; then
  echo "Neither Claude nor Codex refreshed blaise-skills" >&2
  exit 1
fi
python3 "$root/plugins/t3-fleet/skills/t3-fleet-onboard/scripts/sync-plugins.py" || status=1
exit $status
