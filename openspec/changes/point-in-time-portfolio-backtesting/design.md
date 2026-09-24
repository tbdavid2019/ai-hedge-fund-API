# Design

## Context

The API currently builds an empty portfolio from `initialCash`; the analyst workflow passes date ranges to data tools. Financial metrics are filtered by report period, while the repository's `Backtester` already simulates trades and calculates Sharpe, Sortino, and drawdown metrics. These existing paths should be extended rather than replaced. See `proposal.md` and the three capability specs for the required behavior.

## Goals / Non-Goals

**Goals:**

- Make the time a fact became public distinct from the period or event the fact describes.
- Preserve legacy analysis requests while accepting a validated portfolio object.
- Add durable, resumable grid evaluation and benchmark-relative metrics to the existing backtester.

**Non-Goals:**

- Replacing the LangGraph workflow or existing backtest simulation.
- Promising byte-identical LLM output across repeated runs.
- Adding every TradingAgents data vendor, a decision-memory feature, or a broad LLM provider registry.
- Treating unsupported point-in-time sources as safe by inference.

## Decisions

### Normalize availability metadata at the data boundary

Represent the business/event date, public availability time, source identifier, and point-in-time status separately on dated records. Normalize source timestamps to UTC. Use one configured UTC cutoff for every instrument in a multi-market backtest; use the relevant exchange's local close for a standalone single-market date-only analysis. Apply the requested decision cutoff where data enters the agent state, after provider-specific normalization and before cache results are returned to an agent. Cache keys or cached entries must preserve the date range and provenance needed for the same filtering. Do not infer a filing or publication date from a fiscal period or transaction date.

For strict historical runs, exclude records with unknown availability and include a structured reason in the result. Start with sources that expose a trustworthy publication/filing timestamp, such as SEC EDGAR for applicable US filings. Retain existing providers for other data, but do not represent undated historical records as point-in-time verified. Do not use retrospective adjusted price series that incorporate future corporate actions; model price and holdings changes only when an action is effective. Report current-only security-registry coverage as survivorship-biased rather than complete historical-universe coverage.

**Alternative considered:** Filter only in each analyst. This duplicates temporal rules across agents and allows a newly added agent to bypass them.

### Define backtest decisions at a cutoff and execute after it

Treat one configured UTC cutoff before the end date as the information boundary for each portfolio decision session. All ticker analyses on that session use records available by the shared cutoff and see the same pre-trade portfolio; aggregate decisions and execute trades as one batch only after the cutoff. Use the end date only for final valuation, so no unfilled end-date order enters the result. A grid run maintains one portfolio state across the interval and applies the selected daily rebalance policy. Report portfolio return and risk metrics over the full interval. Preserve existing position accounting while adding explicit benchmark mapping, transaction fees, and slippage assumptions.

**Alternative considered:** Keep same-close fills for compatibility. This preserves a fast but optimistic simulation and conflicts with point-in-time evaluation.

### Keep portfolio input optional and explicit

Accept a top-level `portfolio` object with `as_of`, `cash`, cash `currency`, and a list of positions containing ticker, signed quantity, average entry price, and position currency. Use point-in-time foreign-exchange data to convert non-cash-currency holdings; reject a request when no suitable rate is available. If `portfolio` is omitted, retain the legacy `initialCash` behavior. If present, the portfolio object's cash takes precedence over `initialCash`; an empty positions list means explicitly flat. For historical runs, require the initial portfolio snapshot to match the run start date. Validate the request before starting synchronous or asynchronous work, then normalize it once into the workflow's existing internal portfolio representation.

**Alternative considered:** Replace `initialCash` with a required portfolio. That would break existing clients without improving users who do not track holdings.

### Persist grid results transactionally and bind them to a configuration fingerprint

Use a local SQLite run store (built-in Python support) for the run manifest, normalized data snapshots, and per-ticker/date decisions. Store a fingerprint of the date grid, UTC cutoff, tickers, model/provider, analyst selection, starting portfolio, point-in-time mode, benchmark map, rebalance policy, and cost assumptions. Materialize and persist the full run's normalized point-in-time data and source/version identifiers before processing its first decision session. A resume with a mismatched run fingerprint must fail; all sessions reuse the saved snapshots even if a provider later revises its history. Commit each completed session's ticker decisions and resulting portfolio state together so interruption does not leave a partially applied multi-ticker batch. Keep run data outside source-controlled registry data and make the database location configurable for persistent deployment storage.

Store the model output and normalized inputs/provenance for completed cells. A resumed run reuses completed cells; a newly executed cell can still vary because an LLM provider may be nondeterministic.

**Alternative considered:** Store only a JSON/CSV summary. A summary cannot safely identify completed cells or prevent a changed configuration from reusing stale results.

### Report benchmark-relative results with an explicit fallback

Reuse the repository's stock resolver and a versioned benchmark mapping to select a regional benchmark. For a multi-ticker portfolio, build a composite benchmark using each ticker's starting invested-value weight, or equal weights when the starting portfolio is flat. Calculate benchmark return over the same dates as the strategy and report the difference in percentage points. If no benchmark is mapped, preserve absolute metrics and report benchmark-relative metrics as unavailable with a reason; do not silently substitute a US benchmark for another market.

Require the evaluation configuration to carry transaction-fee and slippage assumptions. Do not silently assume zero costs. The initial interface can provide documented baseline values while allowing callers to override them; persist the effective values in every run manifest.

## Risks / Trade-offs

- [Many current providers may not expose historical availability timestamps] → Exclude those records in strict historical mode and report the reduced coverage; add provider adapters only when their dates can be verified.
- [Strict point-in-time filtering can produce sparse historical analyses] → Return coverage and exclusion details so callers can distinguish incomplete evidence from neutral evidence.
- [SQLite durability and full-run input snapshots require persistent storage] → Make the path configurable, estimate storage use, and document a persistent Docker volume before enabling long-running server evaluations.
- [Benchmark mappings can be imperfect across markets and asset classes] → Keep mappings explicit, persist the selected benchmark per cell, and report unavailable cases.
- [Fee and slippage assumptions affect results materially] → Include both in run configuration and returned results; do not imply that backtest returns predict future performance.
- [New portfolio payloads can contain ambiguous duplicate tickers or currencies] → Normalize tickers before validating, reject conflicting duplicates, and require a single cash currency in the initial API contract.

## Migration Plan

1. Add data provenance and availability handling without changing the existing non-historical response shape.
2. Add the optional `portfolio` request field; keep omitted-field defaults and existing aliases intact.
3. Add the evaluation store and grid-run interface alongside the existing single-run backtester.
4. Update OpenAPI, `README.md`, `skill.md`, and `static/skill.md` for the new request and evaluation behavior.
5. Configure a persistent evaluation database path for deployments before enabling resume across server restarts.

Rollback can disable the new grid evaluation path and ignore the optional portfolio field. Existing requests and existing backtest invocation remain supported.
