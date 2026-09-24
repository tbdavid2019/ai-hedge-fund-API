# Tasks

## 1. Point-in-Time Data Contract

- [ ] 1.1 Add normalized business date, public availability time, source identifier, and point-in-time status to dated data records; verify model tests distinguish report period from availability time.
- [ ] 1.2 Apply strict cutoff filtering at the data/cache boundary, normalize time zones, and return source coverage plus exclusion reasons; verify fixtures exclude future filings/news, unknown-availability records, and timestamps after both exchange-local and shared UTC cutoffs.
- [ ] 1.3 Add at least one trustworthy filing-date source adapter for eligible US securities; verify it uses filing/publication time and does not infer availability from fiscal period.
- [ ] 1.4 Prevent future-adjusted prices and corporate actions from entering historical results, and report current-only security-registry coverage as survivorship-biased; verify split, dividend, and delisted-security scenarios.
- [ ] 1.5 Update data-provider documentation with supported point-in-time sources and limitations; verify each source's documented status matches adapter behavior.

## 2. Portfolio-Aware Analysis API

- [ ] 2.1 Add validation and normalization for optional portfolio `as_of`, cash, cash currency, position currency, signed quantity, and average entry price; verify legacy `initialCash` precedence, malformed portfolio rejection, stale snapshots, and missing point-in-time FX rates.
- [ ] 2.2 Pass normalized positions and cash to risk and portfolio agents; verify a long holding, a short holding, and an explicitly empty positions list reach decision inputs correctly.
- [ ] 2.3 Document portfolio date/currency fields, FX handling, optional request behavior, and precedence rules in `static/swagger.json`, `README.md`, `skill.md`, and `static/skill.md`; verify all published schemas describe the same contract and legacy behavior.

## 3. Resumable Backtest Evaluation

- [ ] 3.1 Add a configurable SQLite run store with run manifests, starting portfolio, full-run normalized input snapshots and source versions, portfolio-state checkpoints, and configuration fingerprints; verify a resumed run reuses its original data after provider revisions, preserves completed cells, and rejects changed run identity.
- [ ] 3.2 Add continuous ticker/date-grid execution across a configured start/end interval with one UTC cutoff, explicit daily rebalance policy, shared pre-trade session snapshots, batched orders, and next-tradable-price fills; verify a cross-market fixture grid preserves portfolio state, avoids pre-cutoff fills, and creates no unfilled end-date order.
- [ ] 3.3 Add versioned regional benchmark mapping, a composite benchmark weighted by starting holdings (equal-weighted for a flat portfolio), transaction fees, and slippage; verify matched intervals, benchmark weights, and unavailable cases.
- [ ] 3.4 Return and persist run configuration, point-in-time coverage, source exclusions, benchmark selection, cost assumptions, and existing risk metrics; verify serialized results contain the full evaluation manifest.
- [ ] 3.5 Document the grid-run interface, resume behavior, configurable database location, persistent deployment storage, benchmark limits, and cost assumptions; verify the documented invocation matches the implemented interface.

## 4. Integration and Compatibility

- [ ] 4.1 Run the repository's focused data, portfolio, and backtest test suites; verify historical cutoff, request compatibility, resume, benchmark, and execution-cost scenarios pass together.
- [ ] 4.2 Run the documented Python syntax verification for modified modules and validate the OpenAPI document; verify the existing analysis endpoint remains usable without new request fields.

## 5. Follow-Up Architecture Assessment

- [ ] 5.1 After the core run store and grid evaluation are integrated, assess whether LangGraph checkpoint recovery adds value beyond committed session state; verify a written recommendation covers restart behavior, graph compatibility, persistent storage, operational cost, and go/no-go.
- [ ] 5.2 Assess persistent decision logs or reflection memory after point-in-time protections are complete; verify a written recommendation covers leakage risk, reproducibility, privacy/retention, measurable benefit, opt-in boundaries, and go/no-go, with a separate follow-up proposal if accepted.
