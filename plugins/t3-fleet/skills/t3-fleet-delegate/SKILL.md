---
name: t3-fleet-delegate
description: "Use when delegating between Opus and Sol helps."
---

# Delegation rules

T3's own instructions cover how to delegate. These rules override its
defaults and examples.

- You don't need permission to delegate within the user's task. Tell the
  user in one line what you delegated and to whom.
- Default split: **Opus plans, Sol executes.** If Sol is unavailable, Opus
  executes. Choose as you see fit.
- Always set the effort and service tier in `target.options`; don't rely on
  inherited values or T3's examples.
  - Effort: pick what the task needs, from `low` to `xhigh`. Never use `max`
    or anything above it. Use `xhigh` only when the task needs it, because
    it's slow and costly.
  - Service tier: standard. Never fast/priority.

  | Agent | `providerInstanceId` | `model` | Options |
  |---|---|---|---|
  | Sol | `codex` | `gpt-6.1-sol` | `{"reasoningEffort": "<effort>", "serviceTier": "default"}` |
  | Opus | `claudeAgent` | `claude-opus-5-5` | `{"effort": "<effort>", "fastMode": false}` |

- The child runs on your own box; T3 can't delegate to another box. To work
  on another box, run commands there over SSH as `AGENTS.md` describes.
- The brief: the child has your `AGENTS.md`, skills, and git setup, but not
  your conversation. Give it the goal and why, what you already know, where
  to work, and what done looks like. Add only limits it couldn't infer, with
  reasons. Don't restate rules it already loads, script its steps, or forbid
  things it can judge, including which subagents it uses. Trust it.
- Verify what the child claims before you rely on it.
