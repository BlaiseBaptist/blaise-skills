---
name: t3-fleet-delegate
description: For Opus and Sol only. Hand a task to another agent (Opus, Sol, Sonnet, Luna, or Haiku) running as a real T3 Code thread on a fleet box; your thread gets a message when it finishes. The default split is Opus plans, Sol executes, Luna does mechanical changes. Use on your own initiative, without asking first, when a settled plan needs executing, when an independent review by a different model would catch what you might miss, when work splits into independent pieces that can run in parallel, when the work belongs on another box, or when a long job would otherwise block you. Also use when the user asks to delegate.
---

# Delegate to another T3 agent

The bundled helper starts an ordinary, visible T3 thread on the chosen box and
posts a message into your thread when it finishes. The child is a peer, not a
script runner: brief it the way you'd brief a capable colleague.

Only Opus and Sol delegate. The helper checks which model is calling it and
refuses everyone else.

## When to delegate

You don't need permission. A task the user gave you includes authority to
delegate parts of it. Delegate when:

- **The plan is made and execution remains.** Once a plan is settled, hand
  implementation and mechanical edits to a lower tier, then review what comes
  back.
- **A second opinion matters.** You wrote or decided something consequential
  (a design, a risky change, a release). A different model family reviewing
  it cold catches different mistakes: Sol for Opus's work, Opus for Sol's.
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

| Agent | `--model` | Role |
|---|---|---|
| Opus | `opus` | Planning, design, judgment calls; reviewing Sol's execution |
| Sol | `sol` | Executing a plan: implementation, debugging, ports; reviewing Opus's plans |
| Sonnet | `sonnet` | Execution when Sol is unavailable or out of limits |
| Luna | `luna` | Mechanical changes: renames, bulk edits, follow-the-pattern rewrites |
| Haiku | `haiku` | Lookups and smoke checks |

The split is a default, not a rule; choose as you see fit, including a
stronger model than yourself when the task needs it.

Pass `--effort` (`low`, `medium`, `high`, or `xhigh`) as what you judge the
task needs. The helper launches the child one level lower, because Opus and Sol
tend to overestimate, and never uses `max`.

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
  such as fetching, reading code, running tests, or delegating further.

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

Children run with full access, like T3 sessions on the fleet. Add `--plan`
to start one in plan mode.

```sh
python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux start \
  --cwd /home/blaise/T3_code_improvements \
  --model sol --effort high \
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

Carry on with other work. When the child finishes, your thread gets a
`[t3-fleet]` message with its state and thread ID, which starts a new turn if
you're idle. Then `read` it; that returns the final answer, or every message
with `--full`.

Then read the result and **check it before you relay it**. `completed` means
the turn ended, not that it succeeded. Spot-check concrete claims: the branch
or PR exists, the SHAs are right, tests were actually run. `interrupted` is not
success, and `error` or `lastError` needs a look. Report to the user what the
child found or did, what you verified, and what remains.

The child's commits stay on its box. If you need them elsewhere, ask the child
to push a branch, or fetch it over SSH:
`git fetch ssh://blaise@<host>.tail2b35ba.ts.net/<path> <branch>`.

Other commands, each taking the machine then the thread ID:

- `read`: the child's state and final answer.
- `wait`: like `read`, but waits up to 50 seconds for it to finish.
- `send`: a follow-up message, read from stdin.
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

These are plain sidebar threads with no parent link; track the relationship in
the title. The completion message comes from a watcher process on your box. It
gives up after a day, or after half an hour of the child's box being
unreachable, and posts that instead. A shell-launched `codex exec` or `claude -p` is not
a substitute: it bypasses T3's thread ownership and visibility.

Each command issues a two-minute T3 bearer on the target and revokes it
afterward. It carries T3's broad CLI scopes. Never print or store it, inspect
T3's secrets directory, or trace the shell around it.
