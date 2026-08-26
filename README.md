# SaaS Implementation Operations Lab

[![Quality](https://github.com/Jsantiagom11/saas-implementation-ops-lab/actions/workflows/quality.yml/badge.svg)](https://github.com/Jsantiagom11/saas-implementation-ops-lab/actions/workflows/quality.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-4fe1a1)

An executable portfolio case study that models the operational control plane behind a SaaS implementation: customer onboarding, governed stage transitions, delivery metrics and an immutable audit trail.

**[Read the business and engineering case study →](docs/case-study.md)**

## Why this exists

Implementation teams often manage critical delivery state across spreadsheets, chat and CRM notes. This project demonstrates how to turn that fragmented workflow into a small, auditable product with explicit business rules.

## Capabilities

- Customer implementation pipeline from discovery to hypercare
- Guarded transitions that prevent skipped delivery gates
- SQLite persistence with transactions and foreign keys
- WAL mode, bounded lock waiting and optimistic version checks
- Audit history for operational accountability
- Portfolio and adoption dashboard
- UTC-normalized, configurable SLA and go-live risk scoring with reason codes
- Responsive, dependency-free web interface
- Typed API contracts and automated lifecycle tests
- Integer-cent money storage with exact decimal API totals

## Architecture

```mermaid
flowchart TD
    UI[Operations dashboard] --> API[FastAPI endpoints]
    API --> SVC[Business rules]
    SVC --> DB[(SQLite)]
    SVC --> AUDIT[Audit events]
    AUDIT --> DB
```

The separation between HTTP routes, domain service and persistence keeps the business rules testable and makes a future PostgreSQL or CRM integration straightforward.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn saas_ops.main:app --reload
```

Open `http://127.0.0.1:8000`. Interactive API documentation is available at `/docs`.

Risk thresholds are configured at startup. Invalid or reversed values fail fast:

| Environment variable | Default | Constraint |
|---|---:|---|
| `SAAS_OPS_STAGE_WARNING_HOURS` | `48` | Integer >= 0 |
| `SAAS_OPS_STAGE_BREACH_HOURS` | `72` | Integer > stage warning |
| `SAAS_OPS_GO_LIVE_WARNING_HOURS` | `168` | Integer >= 0 |

API timestamps must include a timezone offset and are normalized to UTC for exact-duration
comparisons. Future stage timestamps surface a high-risk data-quality reason instead of being
silently clamped. Risk is recalculated on reads; `risk_reasons[].code` is the stable integration
contract and human-readable messages are presentation text.

Transitions require the customer's current `version`. A stale request returns HTTP `409`
instead of overwriting a newer milestone.

Create the first implementation:

```bash
curl -X POST http://127.0.0.1:8000/api/customers \
  -H 'content-type: application/json' \
  -d '{"name":"Andes Telecom","owner":"Jorge Santiago","target_go_live":"2026-10-01T12:00:00Z","contract_value":48000}'
```

## Quality gates

```bash
make check
```

This runs Ruff, strict mypy and pytest. No credentials or external services are needed. The
suite includes exact SLA boundaries, timezone equivalence, invalid configuration, schema
migration, concurrent transitions, SQLite pragmas, stale API requests, exact money totals and
web-output escaping. See [Rainy-day testing](docs/rainy-day-testing.md).

## Decisions and trade-offs

| Decision | Rationale | Production evolution |
|---|---|---|
| SQLite + WAL | Zero-friction evaluation with deterministic write contention | PostgreSQL for multi-instance deployment |
| Optimistic versions | Rejects stale stage transitions | ETag/idempotency contracts at integration boundaries |
| Integer cents | Exact financial totals | Currency-aware money type for multi-currency accounts |
| Sequential stages | Makes governance visible | Configurable workflows |
| Synchronous API | Appropriate for current workload | Task queue for imports |
| Vanilla dashboard | Keeps the case inspectable | Component UI if scope grows |

## Roadmap

- CSV data-import validation and error reports
- Per-stage SLA policies and escalation notifications
- Role-based access control
- Webhooks for CRM and messaging integrations
- OpenTelemetry metrics and structured logs

See [CHANGELOG.md](CHANGELOG.md) for released capabilities and evolution.

## Professional context

Built as a product-engineering case study at the intersection of SaaS implementation, operational delivery, workflow automation and troubleshooting.
