# blaise-skills

Blaise's shared Claude Code and Codex skills, published as a plugin marketplace
named `blaise-skills` and installed on the T3 Code fleet.

## Install

```sh
claude plugin marketplace add https://github.com/BlaiseBaptist/blaise-skills.git
claude plugin install t3-fleet@blaise-skills --scope user
```

Use the HTTPS URL. The `owner/repo` shorthand clones over SSH, and the fleet
boxes have no GitHub SSH key. Both commands are idempotent.

## Plugins

| Plugin     | Skills                                          | Install on          |
| ---------- | ----------------------------------------------- | ------------------- |
| `t3-fleet` | `t3-fleet-onboard`, `t3-fleet-delegate`           | every box         |
| `desktop`  | `screenshot`                                    | boxes with a display |

Plugin skills are namespaced: `/t3-fleet:t3-fleet-onboard`, not `/t3-fleet-onboard`.
Use `/t3-fleet:t3-fleet-delegate` for cross-machine or cross-model T3 agents.
In Codex, invoke `$t3-fleet:t3-fleet-delegate` or `$t3-fleet:t3-fleet-onboard`.

## Layout

```
.claude-plugin/marketplace.json    catalog
plugins/<plugin>/
  .claude-plugin/plugin.json       manifest
  skills/<skill>/SKILL.md          skill, with its own scripts/ and references/
```

Inside a SKILL.md, resolve helpers relative to the directory containing that
loaded skill. Both harnesses supply its absolute path. Shell examples use
`SKILL_DIR` for that directory; do not depend on Claude-specific variable
expansion or tool names for a shared workflow.

## Claude and Codex

The repo is a plugin marketplace for both harnesses. Claude reads
`.claude-plugin/marketplace.json` and each plugin's `.claude-plugin/plugin.json`;
Codex reads `.agents/plugins/marketplace.json` and `.codex-plugin/plugin.json`.
Both manifests point at the same `skills/` folders, so there is one authored
copy.

`~/.local/bin/claude-skills-sync` updates each harness from GitHub through its
own plugin system, and a failure in one doesn't stop the other. On a box whose
Codex has no `blaise-skills` plugins yet, it installs the ones Claude has, or
`t3-fleet`. It also keeps itself current from the updated repo. Requires
Python 3; Codex need not be running.

Earlier versions linked skills into `~/.agents/skills` for Codex instead. The
first run of this sync hands over from that one and removes only the links it
recorded in `~/.local/state/blaise-skills/shared-links.json`, once Codex has
its own install. Other links there, such as Claude.ai's synced document
skills, are left alone. Do not duplicate these skills under `~/.claude/skills`
or `~/.agents/skills`, which would make a harness load them twice.

New sessions load the new skills. Restart an existing agent if discovery is
stale; no T3 server restart is needed.

## Versioning

No `version` field in any `plugin.json`, so each plugin's version resolves to
this repo's commit SHA for Claude, and Codex refreshes its installed copy on
every marketplace upgrade. Every push reaches the fleet on the next sync. Add a
`version` to a `plugin.json` to hold boxes still until you bump it.

Sync runs hourly from a systemd user timer on Linux (`claude-skills-sync.timer`)
or the existing launchd job on the Macs;
see the `t3-fleet-onboard` skill. Claude Code's own background auto-update fires
after a random delay of up to ten minutes, and T3-launched turns are usually
shorter than that, so it misses most of them.

Validate the sync with
`python3 -m unittest discover -s tests`.
