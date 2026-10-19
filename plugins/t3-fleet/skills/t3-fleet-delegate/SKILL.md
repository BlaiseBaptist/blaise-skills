---
name: t3-fleet-delegate
description: "Use when delegating between Opus and Sol helps."
---

# Delegate to another T3 agent

You don't need permission to delegate within the user's task. Tell the user in
one line what you delegated and to whom.

Default split: **Opus plans, Sol executes.** If Sol is unavailable, Opus
executes. Choose as you see fit.

Use T3's own `delegate_task` tool (from the `t3-code` MCP server). It runs
child agents for any provider, so Opus can start Sol and Sol can start Opus.
Don't shell out to `codex exec` or `claude -p`.

| Agent | `providerInstanceId` | `model` | Effort option |
|---|---|---|---|
| Sol | `codex` | `gpt-6.1-sol` | `reasoningEffort` |
| Opus | `claudeAgent` | `claude-opus-5-5` | `effort` |

Set the effort you judge the task needs, from `low` to `xhigh`. Never use
`max` or anything above it. Use `xhigh` only when the task needs it, because
it's slow and costly. If an ID is rejected, check `orchestrator_capabilities`.

```json
{"task": "<brief>", "title": "Sol: <task> (for Opus)",
 "target": {"providerInstanceId": "codex", "model": "gpt-6.1-sol",
            "options": {"reasoningEffort": "high"}},
 "mode": "async", "clientRequestId": "<unique-id>"}
```

The child shares your checkout. Pass `"isolation": "worktree"` for parallel
edits: it starts from your last local commit, and uncommitted edits aren't
copied. Reuse a `clientRequestId` only to retry the same launch.

The child runs on your own box. T3 can't delegate to another box. To work on
another box, run commands there over SSH as `AGENTS.md` describes.

## The brief

The child has the same `AGENTS.md`, skills, and git setup as you, but not your
conversation. Give it the goal and why, what you already know, where to work,
and what done looks like. Add only the limits it couldn't infer, with reasons.
Don't restate rules it already loads, script its steps, or forbid things it
can judge, including which subagents it uses. Trust it.

## Results

With `mode: "async"`, end your turn. T3 wakes your thread when the child
finishes, and its final answer is its report. Verify what it claims before
you rely on it. Use `task_status` to read a result mid-turn, and use
`task_cancel` to stop a child. For another review round, call
`delegate_task` again with the full context and a new `clientRequestId`.
