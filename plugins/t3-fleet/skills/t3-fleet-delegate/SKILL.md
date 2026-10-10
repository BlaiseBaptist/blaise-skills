---
name: t3-fleet-delegate
description: Hand a task to another agent (Opus, Sol, Sonnet, Luna, or Haiku) running as a real T3 Code thread on a fleet box, then collect its result. The default split is Opus plans, Sol executes, Luna does mechanical changes. Use on your own initiative, without asking first, when a settled plan needs executing, when an independent review by a different model would catch what you might miss, when work splits into independent pieces that can run in parallel, when the work belongs on another box, or when a long job would otherwise block you. Also use when the user asks to delegate.
---

# Delegate to another T3 agent

The bundled helper starts an ordinary, visible T3 thread on the chosen box. That
box's T3 launches the provider with its own auth and config, and you collect the
result with the same helper. The child is a peer, not a script runner: brief it
the way you'd brief a capable colleague.

## When to delegate

You don't need permission. A task the user gave you includes authority to
delegate parts of it. Delegate when:

- **The plan is made and execution remains.** Once a plan is settled, hand
  implementation and mechanical edits to a lower tier, then review what comes
  back.
- **A second opinion matters.** You wrote or decided something consequential
  (a design, a risky change, a release). A different model family reviewing
  it cold catches different mistakes. Opus can ask Sol to review; Sol can't
  ask Opus.
- **The work splits.** Two or more pieces touch different files or repos and
  don't need each other's results. Run them in parallel, each in its own
  worktree.
- **The work belongs elsewhere.** It needs the Mac, another box's checkout,
  container, or hardware.
- **It's long.** A port, a sweep, or a bulk refactor that would hold up the
  conversation for an hour.

Don't delegate work that is quicker to do than to brief, that needs back and
forth with the user, or whose context is mostly in your head and expensive to
write down. Delegation stays inside the user's task; it doesn't authorize
unrelated work.

When you delegate, tell the user in one line: box, model, thread title.

## Choose the agent and effort

The default split: **Opus plans, Sol executes, Luna does mechanical changes.**
Opus works out what to do and why, Sol carries out the plan, and repetitive or
mechanical edits go to Luna. When Sol's work comes back, Opus reviews it.

| Tier | Agent | `--provider` | `--model` | Role |
|---|---|---|---|---|
| 1 | Opus | `claudeAgent` | `claude-opus-5-5` | Planning, design, judgment calls; reviewing Sol's execution |
| 2 | Sol | `codex` | `gpt-6.1-sol` | Executing a plan: implementation, debugging, ports; reviewing Opus's plans |
| 3 | Sonnet | `claudeAgent` | `claude-sonnet-5-5` | Execution when Sol is unavailable or out of limits |
| 4 | Luna | `codex` | `gpt-6-luna` | Mechanical changes: renames, bulk edits, follow-the-pattern rewrites |
| 5 | Haiku | `claudeAgent` | `claude-haiku-5-5` | Lookups and smoke checks |

The split is a default, not a rule; choose as you see fit. The one hard rule:
**delegate only to your own tier or below, never up.** Sol never delegates to
Opus, and Luna never to Sonnet or Sol. If a task turns out to need a stronger
model than you may delegate to, say so in your result instead.

Haiku 5.5 isn't in T3 0.0.45's model picker, but T3 passes the ID through and
it runs.

Pick effort for the task, not by habit. It can be higher or lower than your
own.

- `low`: mechanical edits, smoke tests, lookups.
- `medium`: ordinary implementation, reviews of small changes.
- `high`: subtle debugging, numerics or concurrency, reviews where a miss is
  expensive.
- `xhigh`: genuinely hard problems where `high` fell short. Slow and costly.

**`max` is forbidden**, along with everything above it: Sol's `ultra` and
Claude's `ultrathink` and `ultracode`. The helper refuses them.

**Opus and Sol: take one level off.** Decide the effort you think the task
needs, then delegate one level below it: `high` becomes `medium`, `medium`
becomes `low`. `low` stays `low`. Other agents use the effort they judge
right.

Pass options as JSON with `--options`:

- Claude: `effort`, `fastMode` (boolean), `contextWindow` (`200k` or `1m`,
  default `1m`). Omitted `effort` means `medium`.
- Codex: `reasoningEffort` and `serviceTier`. Always set `reasoningEffort`:
  omitted, Sol runs at `low` and Luna at `medium`.

The helper doesn't validate models. A model the box lacks fails at launch;
read the result before assuming it ran as asked.

## Write the brief

The child loads the same `AGENTS.md`, `CLAUDE.md`, skills, and git config on
its box that you would. It does not see your conversation. The brief carries
what it can't find on its own:

- **Goal and why.** What outcome, and what it's for. The why lets the child
  make the calls you didn't anticipate.
- **What you already know.** Verified facts and how you verified them, so it
  doesn't redo your work. Label it as context, not orders.
- **Where.** Target-local repo or worktree path and branch.
- **Done.** The deliverable, and what you'll check when it comes back.
- **Real limits, with reasons.** Only constraints the child can't infer and
  that are costly to get wrong: shared branches it must not push, another
  agent's worktree, a shared container, anything the user ruled out.

Leave out:

- **Rules it already loads.** Git identity, signing, attribution, memory, and
  project `AGENTS.md` conventions reach the child without you. Repeating them
  buries the limits that matter.
- **Recipes.** Describe the outcome, not the commands. If you have a view on
  the approach, offer it as a suggestion and ask the child to say where it went
  another way and why.
- **Blanket prohibitions.** No caps on things the child can judge for itself,
  such as fetching, reading code, running tests, or delegating further. The
  child follows this skill's tier rule on its own.

A good brief is usually well under a page. If yours is growing past that,
either point the child at a file on its box that holds the context, or split
the task.

## Launch

Find the target-local workspace with `projects`. The workspace must already be
a registered T3 project on that box; Linux paths are `/home/blaise/...`, the
Mini's are `/Users/blaise/...`. The helper doesn't copy files. For parallel or
concurrent edits, create a worktree on the target and pass
`--worktree /absolute/path`.

```sh
python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux projects
```

Run the child with `--runtime-mode full-access` when you have full access
yourself, as T3 sessions on the fleet do. The helper's default,
`approval-required`, parks the child on its first approval with nobody watching
the thread. Use it only when the user wants to approve the child's actions in
T3 themselves.

```sh
python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux start \
  --cwd /home/blaise/T3_code_improvements \
  --provider codex --model gpt-6.1-sol --options '{"reasoningEffort":"medium"}' \
  --runtime-mode full-access \
  --title 'Sol: review sync timer change (for Opus)' \
  --request-id sync-timer-review-1 <<'TASK'
I changed the claude-skills sync timer to run every 15 minutes instead of
hourly (diff below). I want an independent read on whether it is safe before
it rolls out to every box. What worries me is overlapping runs on a slow box
and Claude's plugin cache filling with old versions. Tell me if either is
real, and anything else you'd flag. Change nothing; I'll make the edits.

<diff>
TASK
```

Give each task its own `--request-id` and reuse it to retry the same launch;
the helper then finds the existing thread instead of starting a duplicate. A
new round needs a new ID. Keep the machine and thread ID it returns.

## Follow and collect

Launch without `--wait` and poll in a background shell so you keep working.
The helper waits at most 50 seconds per call and exits nonzero on an `error`
state:

```sh
out=/tmp/t3-child-THREAD_UUID.json
while python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux wait THREAD_UUID --wait 50 >"$out" \
  && grep -q '"waitTimedOut": true' "$out"; do :; done
```

Then read the result and **check it before you relay it**. `completed` means
the turn ended, not that it succeeded. Spot-check concrete claims: the branch
or PR exists, the SHAs are right, tests were actually run. `interrupted` is not
success, and `error` or `lastError` needs a look. Report to the user what the
child found or did, what you verified, and what remains.

The child's commits stay on its box. If you need them elsewhere, ask the child
to push a branch, or fetch it over SSH:
`git fetch ssh://blaise@<host>.tail2b35ba.ts.net/<path> <branch>`.

The helper can't send a follow-up into an existing thread yet. Either continue
in T3 yourself, or start a new round with a new request ID whose brief includes
what came back.

Other commands, each taking the machine then the thread ID:

- `read`: snapshot without waiting.
- `interrupt`: cancel when asked.
- `archive` / `unarchive`: put away finished threads. An archived thread must
  be restored before `read` works.

## Mechanics

Set `SKILL_DIR` to the directory holding this `SKILL.md`, using the absolute
path your harness supplies.
Claude invokes this skill as `/t3-fleet:t3-fleet-delegate`, Codex as
`$t3-fleet:t3-fleet-delegate`. Use the bundled helper, not the stale
`~/.local/bin/t3-fleet-agent` copy.

The helper allows `archlinux`, `war`, and `blaises-mini`; `fleet.md` in
`T3_code_improvements` is the roster. It reaches a box over Tailscale with
batch SSH and needs nothing installed there. If a box is offline or SSH fails,
report it unreachable; don't restore T3 Connect or try another path.

The helper supports **T3 0.0.45** and refuses other versions. If it rejects a
newer T3, check that version's API and update the helper; don't remove the
guard.

These are plain sidebar threads with no parent link or notification. Track the
relationship in the title. A shell-launched `codex exec` or `claude -p` is not
a substitute: it bypasses T3's thread ownership and visibility.

Each command issues a two-minute T3 bearer on the target and revokes it
afterward. It carries T3's broad CLI scopes. Never print or store it, inspect
T3's secrets directory, or trace the shell around it.
