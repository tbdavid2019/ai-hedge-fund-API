# Follow-up Architecture Assessment

## LangGraph checkpoint recovery

**Recommendation: no-go for this change.** The SQLite run store already commits each completed date session atomically with the decision cells, portfolio before/after snapshots, market inputs, metrics, and pending orders. Immutable source snapshots and the configuration fingerprint make a restart deterministic at the next uncommitted session. A LangGraph checkpointer would primarily help recover a process interrupted inside an in-progress session; it would not replace the run manifest, source snapshot, or portfolio ledger.

Before adopting graph-level checkpoints, measure how often interrupted LLM sessions justify the additional persistence, graph state migration, and backend operations. Any later design must bind checkpoints to the same run fingerprint and durable storage, and must not allow a restarted node to fetch newer provider data. Current limitation: interruption during an uncommitted session can repeat that session's LLM calls; completed sessions are preserved.

## Persistent decision log or reflection memory

**Recommendation: no-go for persistent reflection memory.** Historical decision text can contain information published after a simulated cutoff. Reusing it can leak future information, contaminate otherwise reproducible runs, and expose sensitive user portfolio context for longer than needed. The current implementation persists decisions only as part of a run-scoped audit record with source snapshots and a configuration fingerprint; it does not feed those records back into future model prompts.

Reconsider only with a measurable benefit over stateless analysis, explicit opt-in and retention controls, privacy review, and strict availability-time filtering that proves every retrieved memory was available at the decision cutoff. No follow-up proposal is created because the recommendation is not to proceed.
