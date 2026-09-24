# Spec Delta

## Purpose

Analysis decisions must reflect a user's existing holdings, cash, and cost basis when the user supplies that portfolio. This lets risk controls and order recommendations respond to actual exposure while preserving the current request behavior for clients that omit portfolio data.

## ADDED Requirements

### Requirement: Analysis accepts explicit holdings
The analysis API MUST accept an optional portfolio containing an `as_of` date, cash, cash currency, and positions. Each position MUST identify a ticker, signed quantity, non-negative average entry price, and trading currency; positive quantities represent long positions and negative quantities represent short positions. Values in another currency MUST be converted with an exchange rate available by the portfolio's `as_of` date, or the request MUST be rejected with a clear error.

#### Scenario: User supplies an existing portfolio
- **WHEN** an analysis request includes valid cash and positions
- **THEN** the workflow MUST receive those values as the user's current portfolio
- **AND** MUST NOT use a portfolio snapshot dated after the analysis cutoff

#### Scenario: User explicitly supplies a flat portfolio
- **WHEN** an analysis request includes a portfolio with an empty positions list
- **THEN** the workflow MUST treat the portfolio as explicitly flat

#### Scenario: User omits portfolio data
- **WHEN** an analysis request omits the portfolio field
- **THEN** the API MUST preserve the existing default portfolio behavior

#### Scenario: Portfolio payload is invalid
- **WHEN** an analysis request contains a malformed position, unsupported quantity, or invalid cash value
- **THEN** the API MUST reject the request with a client error that identifies the invalid portfolio field

#### Scenario: A position uses another currency
- **WHEN** a position currency differs from the portfolio cash currency
- **THEN** the system MUST convert its value using point-in-time foreign-exchange data available by the portfolio's `as_of` date
- **AND** MUST reject the request if no suitable rate is available

#### Scenario: Historical run uses a starting portfolio
- **WHEN** a backtest uses an explicit starting portfolio
- **THEN** the portfolio snapshot date MUST match the backtest start date
- **AND** its cash and positions MUST be valued using data available on that date

### Requirement: Risk and order decisions use current exposure
When explicit portfolio data is supplied, risk and portfolio decisions MUST consider current positions and cash when describing exposure and recommending actions.

#### Scenario: Recommendation addresses an existing position
- **WHEN** the user holds a ticker included in an analysis request
- **THEN** the risk and portfolio decisions MUST take the holding's direction and size into account
