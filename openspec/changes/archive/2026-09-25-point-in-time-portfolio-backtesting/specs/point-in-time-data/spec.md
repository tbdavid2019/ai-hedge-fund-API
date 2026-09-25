# Spec Delta

## Purpose

Historical analysis and backtesting must use only the market and company information that was available by the requested decision time. Source and availability metadata make temporal coverage and limitations visible to users.

## ADDED Requirements

### Requirement: Historical inputs respect the decision cutoff
For a historical analysis or backtest decision time, the system MUST exclude any input record whose public availability time is after that cutoff. A record's fiscal period, transaction date, or event date MUST NOT be treated as its publication time.

#### Scenario: Financial filing was published after the decision date
- **WHEN** a filing reports a period ending before the decision date but was filed after it
- **THEN** the filing MUST NOT be supplied to that historical decision

#### Scenario: News item was published after the decision time
- **WHEN** a news record's publication time is after the decision cutoff
- **THEN** that record MUST NOT be included in the decision inputs

#### Scenario: Decision uses a synchronized multi-market cutoff
- **WHEN** a backtest includes instruments from different time zones
- **THEN** every instrument's input MUST be limited to information available by the same configured UTC cutoff
- **AND** each resulting order MUST execute only at a tradable price observation after that cutoff

#### Scenario: Decision is made at a market close
- **WHEN** a single-market backtest creates a signal using information available through that exchange's local close
- **THEN** the simulated order MUST fill no earlier than the next tradable price observation after the signal cutoff

#### Scenario: Availability timestamps cross time zones
- **WHEN** a source timestamp and a decision cutoff use different time zones
- **THEN** the system MUST normalize both timestamps to UTC before comparison
- **AND** a standalone single-market date-only decision cutoff MUST use the relevant exchange's local close
- **AND** a multi-market backtest MUST use one configured UTC cutoff for all instruments

#### Scenario: Historical prices include later corporate actions
- **WHEN** a provider returns a retrospectively adjusted price series that includes a split or dividend not effective by the decision time
- **THEN** the system MUST NOT use that future-adjusted value in the historical decision
- **AND** any modeled split or dividend MUST affect holdings or cash only when the action becomes effective

### Requirement: Unknown availability is explicit
The system MUST distinguish a record's business date from its availability date. If an input source cannot establish the availability date for a historical run, the system MUST mark that input as having unknown point-in-time status and MUST exclude it from strict point-in-time results.

#### Scenario: Provider does not supply publication dates
- **WHEN** a historical run requests a record from a provider that has no usable availability timestamp
- **THEN** the record MUST be excluded from strict point-in-time inputs
- **AND** the run result MUST report the excluded source and the reason

### Requirement: Historical data provenance is returned
For historical analysis and backtest results, the system MUST report the data sources and point-in-time coverage used for each decision, including any excluded or unknown inputs.

#### Scenario: Result includes temporal coverage
- **WHEN** a historical analysis or backtest decision completes
- **THEN** its result MUST include the decision cutoff, source identifiers, and point-in-time coverage status

### Requirement: Historical security coverage is disclosed
Strict historical results MUST identify whether the evaluated security universe includes point-in-time listings and delisted securities. The system MUST NOT describe results based on a current-only registry as survivorship-bias-free.

#### Scenario: Historical universe data is incomplete
- **WHEN** the selected instruments come from a current registry without historical membership or delisted securities
- **THEN** the result MUST report that historical universe coverage is incomplete
