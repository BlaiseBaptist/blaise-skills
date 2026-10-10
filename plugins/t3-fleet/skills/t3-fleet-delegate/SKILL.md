---
name: t3-fleet-delegate
description: For Opus and Sol. Hand work to another agent (Opus, Sol, Sonnet, Luna, Haiku) as a real T3 thread on a fleet box; your thread gets a message when it finishes. Use on your own initiative whenever delegating would help, such as executing a settled plan, an independent review, parallel work, work on another box, or a long job.
---

# Delegate to another T3 agent

You don't need permission to delegate within the user's task. Tell the user in
one line what you delegated, where, and to whom.

Default split: **Opus plans, Sol executes, Luna does mechanical changes**.
Sonnet stands in for Luna. If Sol is unavailable, Opus executes, handing parts
to Sonnet. Choose as you see fit.

This skill only crosses providers. For models from your own provider, use your
harness's own subagents; the helper refuses them.

`--effort` is what you judge the task needs; the helper runs the child one
level lower. Models are `opus`, `sol`, `sonnet`, `luna`, `haiku`.

```sh
python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux projects
python3 "$SKILL_DIR/scripts/t3-fleet-agent.py" archlinux start \
  --cwd /home/blaise/T3_code_improvements --model sol --effort high \
  --title 'Sol: <task> (for Opus)' --request-id <unique-id> <<'TASK'
<brief>
TASK
```

`SKILL_DIR` is this skill's directory. Boxes are `archlinux`, `war`,
`blaises-mini`, and `--cwd` must be a T3 project on the target. Pass
`--worktree` for parallel edits. Reuse a `--request-id` only to retry the same
launch.

## The brief

The child has the same `AGENTS.md`, skills, and git setup as you, but not your
conversation. Give it the goal and why, what you already know, where to work,
and what done looks like. Add only the limits it couldn't infer, with reasons.
Don't restate rules it already loads, script its steps, or forbid things it
can judge. Trust it.

## Results

Your thread gets a `[t3-fleet]` message when the child finishes. Then `read`
the thread (`--full` for every message), verify what it claims, and report.
Its commits stay on its box until it pushes them.

Other commands take the box and thread ID: `wait`, `send` (follow-up on
stdin), `interrupt`, `archive`, `unarchive`.
