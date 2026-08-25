# Case study: SaaS implementation control plane

## Executive summary

This portfolio system demonstrates how an implementation team can replace fragmented status tracking with a governed customer-onboarding workflow. It makes delivery stages, ownership, contract exposure and operational history visible through one lightweight control plane.

The project is intentionally scoped as an executable product case—not presented as a deployed OpenLoop or client system.

## Problem

SaaS implementations commonly distribute critical state across spreadsheets, CRM notes, email and chat. This creates predictable failure modes:

- Customers advance without completing delivery gates.
- Risks are discussed but not represented consistently.
- Ownership and status changes are difficult to audit.
- Portfolio managers cannot see implementation exposure quickly.

## Users and decisions

| User | Decision supported |
|---|---|
| Implementation manager | Which customer needs intervention? |
| Implementation specialist | What is the next valid delivery stage? |
| Operations leader | How many implementations are active or at risk? |
| Auditor or stakeholder | Who changed the implementation state and why? |

## Solution

The application provides:

- A sequential implementation lifecycle from discovery through hypercare.
- API-enforced transition rules that prevent skipped stages.
- Transactional SQLite persistence.
- Immutable audit events for customer creation and transitions.
- Portfolio-level contract and delivery metrics.
- A responsive dashboard and interactive API documentation.

## Key engineering decisions

| Decision | Reason | Production evolution |
|---|---|---|
| Domain rules outside HTTP routes | Keeps workflow behavior directly testable | Domain package and service interfaces |
| SQLite | Zero-friction local evaluation | PostgreSQL and schema migrations |
| Sequential delivery stages | Makes governance explicit | Configurable workflow definitions |
| UTC timestamps | Removes timezone ambiguity | User-local rendering with UTC storage |
| Strict mypy + CI | Prevents interface drift | Coverage thresholds and contract tests |

## Validation

- Integration test covers customer creation, transition and audit history.
- Negative test confirms that stages cannot be skipped.
- CI runs Ruff, strict mypy and pytest on every push and pull request.

## Current limitations

- Risk is not yet calculated from configurable SLA thresholds.
- Authentication and role-based permissions are intentionally absent.
- The UI currently favors evaluation speed over full implementation planning.

## Next measurable increment

[Issue #1](https://github.com/Jsantiagom11/saas-implementation-ops-lab/issues/1) introduces deterministic SLA risk scoring, risk reasons and boundary tests.

