---
name: t3-fleet-delegate
description: "Use when choosing models and delegating substantial T3 work across higher and lower model tiers."
---

# Delegation rules

T3's own instructions cover how to delegate. These rules override its
defaults and examples.

- You don't need permission to delegate within the user's task. Tell the
  user in one line what you delegated and to whom.
- Aim for roughly equal token shares across the fleet over a rolling week:
  lower tier = Luna, Haiku, Sonnet; higher tier = Sol, Opus (also Astra).
  Track other models separately until classified. This is a routing target,
  not a requirement to generate tokens or equalize each task.
- On substantial work, Opus and Sol should delegate a useful, bounded execution
  task to a lower-tier model when one can handle it. Keep planning, difficult
  diagnosis, integration decisions, and proportionate verification with the
  higher-tier parent. Prefer Sonnet for ordinary implementation and debugging;
  Luna for specified edits, data extraction, and checks; Haiku for narrow
  lookup or summarization. Handle trivial work directly when delegation would
  cost more than it saves.
- Give the child ownership of the task and concise acceptance criteria. Do
  not repeat its investigation or implementation in the parent. Verify the
  result with targeted evidence, and escalate to Sol or Opus when complexity,
  failed checks, or uncertainty justify it. Delegating Opus to Sol, or Sol to
  Sol, does not improve the lower-tier share.
- For `delegate_task`, set effort and supported service-tier options explicitly
  in `target.options`; don't rely on inherited values or T3's examples.
  - Effort: default to `medium`, and use `low` often, for any task that's
    routine or clearly specified. Go to `high` only when the task needs it,
    and `xhigh` rarely, because it's slow and costly. Never use `max` or
    anything above it.
  - Service tier: standard. Never fast/priority.

  | Agent | `providerInstanceId` | `model` | Options |
  |---|---|---|---|
  | Luna | `codex` | `gpt-6-luna` | `{"reasoningEffort": "<effort>", "serviceTier": "default"}` |
  | Sonnet | `claudeAgent` | `claude-sonnet-5-5` | `{"effort": "<effort>"}` |
  | Haiku | `claudeAgent` | `claude-haiku-5-5` | `{"effort": "<effort>"}` |
  | Sol | `codex` | `gpt-6.1-sol` | `{"reasoningEffort": "<effort>", "serviceTier": "default"}` |
  | Opus | `claudeAgent` | `claude-opus-5-5` | `{"effort": "<effort>", "fastMode": false}` |

- Use models and options reported by the current tools. If the selected model
  is unavailable, report that rather than silently switching. Follow T3's
  native-versus-delegate routing and wait instructions. Fleet commands on
  another box still run directly over SSH as `AGENTS.md` describes; do not
  start an agent there just to run a command.
- The brief: the child has your `AGENTS.md`, skills, and git setup, but not
  your conversation. Give it the goal and why, what you already know, where
  to work, and what done looks like. Add only limits it couldn't infer, with
  reasons. Don't restate rules it already loads, script its steps, or forbid
  things it can judge, including which subagents it uses. Trust it.
- Verify what the child claims before you rely on it.
