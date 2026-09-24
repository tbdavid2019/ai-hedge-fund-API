# Spec Delta

## Purpose

Backtest results must be repeatable enough to compare analysis decisions over a ticker and date grid, resume interrupted evaluations, and show performance relative to an appropriate market benchmark.

## ADDED Requirements

### Requirement: Backtests evaluate a ticker and date grid
The system MUST support a backtest evaluation over multiple tickers and decision dates using a recorded run configuration with explicit start date, end date, one UTC decision cutoff, daily rebalance policy, starting portfolio, and execution assumptions. The run MUST maintain one portfolio state across sessions. At each configured UTC cutoff before the end date, all ticker analyses MUST use data available by that same cutoff and the same pre-trade portfolio snapshot; resulting orders MUST be generated as one batch. Each order MUST execute no earlier than the first tradable price observation after the shared cutoff. The end date is a valuation boundary: the system MUST mark the portfolio and benchmark at that cutoff and MUST NOT create an unfilled order from an end-date signal. The run's portfolio return and risk metrics MUST cover the full configured interval, measured from the starting portfolio value to its value at the end date.

#### Scenario: Evaluate multiple tickers and dates
- **WHEN** a user starts a grid evaluation with multiple tickers and dates
- **THEN** the system MUST produce a result for each completed ticker and date cell
- **AND** MUST produce run-level portfolio metrics over the configured interval

#### Scenario: Same-session analyses share a portfolio snapshot
- **WHEN** the system evaluates multiple tickers on one session
- **THEN** every analysis MUST use the same pre-trade holdings and cash
- **AND** the system MUST apply the resulting orders as one session batch

#### Scenario: Cross-market grid uses one decision cutoff
- **WHEN** a run contains tickers from different exchanges or time zones
- **THEN** every ticker's signal MUST use the same configured UTC cutoff
- **AND** no order may execute before that cutoff

#### Scenario: End date is only a valuation boundary
- **WHEN** the system reaches the configured end date
- **THEN** it MUST calculate final strategy and benchmark values at that close
- **AND** it MUST NOT create an order that cannot be filled within the evaluation interval

### Requirement: Grid evaluations can resume safely
The system MUST assign each evaluation a run identifier and MUST allow an interrupted evaluation to resume without repeating completed cells or overwriting unrelated analysis history. The run identity MUST include the starting portfolio and all execution and benchmark configuration. Before the first decision session, the system MUST persist the full run's normalized point-in-time input snapshots and source/version identifiers; every resumed cell MUST reuse its saved snapshot.

#### Scenario: Resume an interrupted evaluation
- **WHEN** a user resumes a run with the same run identifier and configuration
- **THEN** the system MUST retain completed cell results and process only unfinished cells

#### Scenario: Resume with a changed configuration
- **WHEN** a run identifier is reused with a materially different model, analyst set, date grid, or data configuration
- **THEN** the system MUST reject the resume or require a new run identifier

### Requirement: Results include benchmark-relative performance
Each completed evaluation MUST report portfolio return and risk metrics, the selected benchmark return, and benchmark-relative return over the same evaluation interval. Results MUST record the execution-cost and slippage assumptions used.

For a multi-ticker run, the benchmark result MUST use a composite of the mapped regional benchmarks over the same dates. Weights MUST follow the starting portfolio's invested value by ticker; if the starting portfolio is flat, weights MUST be equal across requested tickers. The run MUST use a consistent end-of-session valuation convention for the strategy and benchmark.

#### Scenario: Compare results against a regional benchmark
- **WHEN** an evaluation completes for a ticker with a supported regional benchmark
- **THEN** its result MUST include portfolio return, benchmark return, and the difference between those returns

#### Scenario: No suitable benchmark is available
- **WHEN** the system cannot resolve a benchmark for an instrument
- **THEN** the result MUST report that benchmark-relative performance is unavailable and state why

#### Scenario: Evaluation reports assumptions
- **WHEN** an evaluation returns performance metrics
- **THEN** the result MUST include its run identifier, model and analyst configuration, data-source coverage, transaction-cost assumptions, and slippage assumptions
