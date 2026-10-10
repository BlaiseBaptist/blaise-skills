---
name: t3-fleet-delegate
description: "Use when delegating between Opus and Sol helps."
---

# Delegate to another T3 agent

You don't need permission to delegate within the user's task. Tell the user in
one line what you delegated, where, and to whom.

Default split: **Opus plans, Sol executes.** If Sol is unavailable, Opus
executes. Choose as you see fit.

This skill is only for Opus and Sol threads; the helper refuses anything else.
`--effort` is what you judge the task needs; the helper runs the child one
level lower.

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
can judge, including which subagents it uses. Trust it.

## Results

The child's final answer is its report, and it arrives in your thread as a
`[t3-fleet]` message when the child finishes. Verify what it claims before
you rely on it. Its commits stay on its box until it pushes them.

Other commands take the box and thread ID: `send` (follow-up on stdin),
`wait`, `read`, `interrupt`, `archive`, `unarchive`.
