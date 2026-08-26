# Rainy-day testing

The test strategy separates deterministic domain boundaries from persistence and HTTP failure
modes. Every test uses an isolated temporary database.

## Automated matrix

| Scenario | Expected behavior |
|---|---|
| Warning and breach minus/at/plus one second | Stable low/medium/high boundary |
| Equivalent UTC and UTC−05 timestamps | Identical risk assessment |
| Naive timestamp | API returns `422` |
| Future stage timestamp | High risk with `stage_timestamp_in_future` |
| Invalid, negative, equal or reversed thresholds | Startup/configuration fails fast |
| Multiple simultaneous reasons | Severity-first deterministic ordering |
| Complete implementation | No active SLA reasons |
| Two transitions using one version | Exactly one succeeds; one conflicts |
| Stale transition through HTTP | `409` with current-version context |
| SQLite write contention | WAL and five-second bounded wait are enabled |
| Legacy REAL money schema | Existing values migrate to integer cents |
| `0.10 + 0.20` contract values | Dashboard returns exact `0.30` |
| More than two decimals or excessive magnitude | API returns `422` |
| Server started outside repository directory | Dashboard file still resolves |
| Customer name or owner contains markup | Dashboard escapes API text |

## Concurrency contract

Clients must send `expected_version` with every transition. The service starts an immediate
SQLite transaction, verifies that version, performs a conditional update and increments the
version atomically. Retrying a timed-out request with the same version is safe: the retry is
rejected if the first request committed.

## Remaining production boundaries

- SQLite protects a single local deployment, not horizontally scaled application instances.
- Authentication and role authorization are intentionally outside this portfolio slice.
- Audit events are append-only by application convention; a production database should add
  database-level immutability controls and backups.
- Multi-currency support requires an explicit currency code rather than assuming dollars.
