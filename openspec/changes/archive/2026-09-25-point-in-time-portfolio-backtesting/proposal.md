# Proposal

## Why

Historical analyses can use values that were revised or published after the requested date, which can make backtest results look better than a real investor could have achieved. The existing backtester also lacks a reproducible ticker/date-grid evaluation contract, and the analysis API does not accept the user's actual holdings.

## What Changes

- Add point-in-time rules for dated market and company data, including provenance and handling for records whose availability date cannot be established.
- Allow analysis requests to carry current portfolio cash, currency, and positions while keeping requests without a portfolio backward compatible.
- Extend backtesting to run resumable ticker/date grids and report benchmark-relative results alongside existing portfolio risk metrics, transaction-cost assumptions, and slippage assumptions.
- Record enough run configuration and data-source metadata to explain and reproduce each evaluation.
- After the core historical-analysis and backtesting work, assess LangGraph checkpoint recovery and persistent decision memory; deliver a go/no-go recommendation and a separate follow-up scope if either is justified.

## Capabilities

### New Capabilities

- `point-in-time-data`: Select only data known by the requested analysis date and preserve source and availability metadata.
- `portfolio-context`: Accept explicit current holdings and use them in risk and portfolio decisions.
- `backtest-evaluation`: Run repeatable ticker/date grids and report portfolio and benchmark-relative performance.

### Modified Capabilities

None.

## Impact

- Data access and cache behavior in `src/tools/api.py` and data models in `src/data/models.py`.
- Point-in-time price adjustment, foreign-exchange conversion, and historical-universe coverage reporting.
- Analysis request parsing in `webui2.py`, workflow state in `src/main.py`, and risk and portfolio agents.
- Existing simulation in `src/backtester.py`, with new evaluation configuration and result records.
- OpenAPI and user-facing API documentation if request or response fields change.
- No new external data provider is required for the first implementation; SEC EDGAR can be considered for US filing dates, with existing providers retained for other markets.
