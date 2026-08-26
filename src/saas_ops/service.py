from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from sqlite3 import Row

from .config import RiskThresholds
from .database import connection
from .models import (
    AuditEvent,
    Customer,
    CustomerCreate,
    Dashboard,
    Risk,
    RiskAssessment,
    RiskReason,
    Stage,
)

STAGE_ORDER = list(Stage)


class CustomerNotFoundError(LookupError):
    pass


class InvalidTransitionError(ValueError):
    pass


class ConcurrentUpdateError(RuntimeError):
    pass


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value.astimezone(UTC)


def score_risk(
    customer: Customer,
    *,
    now: datetime,
    thresholds: RiskThresholds,
) -> RiskAssessment:
    now_utc = _utc(now, "now")
    if customer.stage == Stage.COMPLETE:
        return RiskAssessment(risk=Risk.LOW, reasons=[])

    updated_at = _utc(customer.updated_at, "updated_at")
    target_go_live = _utc(customer.target_go_live, "target_go_live")
    raw_stage_age_hours = (now_utc - updated_at).total_seconds() / 3600
    stage_age_hours = max(0.0, raw_stage_age_hours)
    target_hours = (target_go_live - now_utc).total_seconds() / 3600
    reasons: list[tuple[int, RiskReason]] = []

    if raw_stage_age_hours < 0:
        reasons.append(
            (
                0,
                RiskReason(
                    code="stage_timestamp_in_future",
                    message="The stage timestamp is in the future; verify source clock and data.",
                    observed_hours=abs(raw_stage_age_hours),
                    threshold_hours=0,
                ),
            )
        )

    if stage_age_hours >= thresholds.stage_breach_hours:
        reasons.append(
            (
                0,
                RiskReason(
                    code="stage_sla_breached",
                    message=(
                        "Current stage has exceeded its "
                        f"{thresholds.stage_breach_hours}-hour SLA."
                    ),
                    observed_hours=stage_age_hours,
                    threshold_hours=thresholds.stage_breach_hours,
                ),
            )
        )
    elif stage_age_hours >= thresholds.stage_warning_hours:
        reasons.append(
            (
                1,
                RiskReason(
                    code="stage_sla_warning",
                    message=(
                        "Current stage is approaching its "
                        f"{thresholds.stage_breach_hours}-hour SLA."
                    ),
                    observed_hours=stage_age_hours,
                    threshold_hours=thresholds.stage_warning_hours,
                ),
            )
        )

    pre_go_live = STAGE_ORDER.index(customer.stage) < STAGE_ORDER.index(Stage.GO_LIVE)
    if pre_go_live and target_hours <= 0:
        reasons.append(
            (
                0,
                RiskReason(
                    code="target_go_live_overdue",
                    message="Target go-live is due or overdue.",
                    observed_hours=max(0.0, -target_hours),
                    threshold_hours=0,
                ),
            )
        )
    elif pre_go_live and target_hours <= thresholds.go_live_warning_hours:
        reasons.append(
            (
                1,
                RiskReason(
                    code="target_go_live_approaching",
                    message=(
                        "Target go-live is within the "
                        f"{thresholds.go_live_warning_hours}-hour warning window."
                    ),
                    observed_hours=max(0.0, target_hours),
                    threshold_hours=thresholds.go_live_warning_hours,
                ),
            )
        )

    reasons.sort(key=lambda item: (item[0], item[1].code))
    risk = Risk.HIGH if any(severity == 0 for severity, _ in reasons) else (
        Risk.MEDIUM if reasons else Risk.LOW
    )
    return RiskAssessment(risk=risk, reasons=[reason for _, reason in reasons])


def _customer(
    row: Row,
    *,
    now: datetime,
    thresholds: RiskThresholds,
) -> Customer:
    values = dict(row)
    values["contract_value"] = Decimal(values.pop("contract_value_cents")) / 100
    customer = Customer(**values)
    assessment = score_risk(customer, now=now, thresholds=thresholds)
    return customer.model_copy(
        update={"risk": assessment.risk, "risk_reasons": assessment.reasons}
    )


def create_customer(payload: CustomerCreate) -> Customer:
    thresholds = RiskThresholds.from_env()
    now_datetime = datetime.now(UTC)
    now = now_datetime.isoformat()
    cents = int((payload.contract_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    with connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
        if "contract_value" in columns:
            cursor = conn.execute(
                """INSERT INTO customers
                (name, owner, target_go_live, contract_value, contract_value_cents,
                 stage, risk, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (payload.name, payload.owner, payload.target_go_live.isoformat(),
                 float(payload.contract_value), cents, Stage.DISCOVERY, Risk.LOW, now, now),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO customers
                (name, owner, target_go_live, contract_value_cents,
                 stage, risk, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (payload.name, payload.owner, payload.target_go_live.isoformat(),
                 cents, Stage.DISCOVERY, Risk.LOW, now, now),
            )
        customer_id = int(cursor.lastrowid or 0)
        conn.execute(
            """INSERT INTO audit_events
            (customer_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)""",
            (customer_id, payload.owner, "customer.created", "Implementation opened", now),
        )
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    assert row is not None
    return _customer(row, now=now_datetime, thresholds=thresholds)


def list_customers() -> list[Customer]:
    thresholds = RiskThresholds.from_env()
    now = datetime.now(UTC)
    with connection() as conn:
        rows = conn.execute("SELECT * FROM customers ORDER BY updated_at DESC").fetchall()
    return [_customer(row, now=now, thresholds=thresholds) for row in rows]


def transition(
    customer_id: int,
    stage: Stage,
    actor: str,
    note: str,
    expected_version: int,
) -> Customer:
    thresholds = RiskThresholds.from_env()
    now_datetime = datetime.now(UTC)
    now = now_datetime.isoformat()
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise CustomerNotFoundError(customer_id)
        if row["version"] != expected_version:
            raise ConcurrentUpdateError(
                f"Stale customer version: expected {expected_version}, current {row['version']}"
            )
        current = Stage(row["stage"])
        current_index = STAGE_ORDER.index(current)
        if current == Stage.COMPLETE:
            raise InvalidTransitionError("Customer implementation is already complete")
        expected = STAGE_ORDER[current_index + 1]
        if stage != expected:
            raise InvalidTransitionError(f"Expected {expected}")
        stable_stages = {Stage.GO_LIVE, Stage.HYPERCARE, Stage.COMPLETE}
        risk = Risk.LOW if stage in stable_stages else row["risk"]
        cursor = conn.execute(
            """UPDATE customers
            SET stage = ?, risk = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND version = ?""",
            (stage, risk, now, customer_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ConcurrentUpdateError("Customer changed during transition")
        conn.execute(
            """INSERT INTO audit_events
            (customer_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)""",
            (customer_id, actor, "stage.transitioned", f"{current} -> {stage}: {note}", now),
        )
        updated = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    assert updated is not None
    return _customer(updated, now=now_datetime, thresholds=thresholds)


def audit_log(customer_id: int) -> list[AuditEvent]:
    with connection() as conn:
        exists = conn.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if exists is None:
            raise CustomerNotFoundError(customer_id)
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE customer_id = ? ORDER BY id DESC", (customer_id,)
        ).fetchall()
    return [AuditEvent(**dict(row)) for row in rows]


def dashboard() -> Dashboard:
    customers = list_customers()
    stage_counts = {stage.value: 0 for stage in Stage}
    for customer in customers:
        stage_counts[customer.stage.value] += 1
    return Dashboard(
        total_customers=len(customers),
        active_implementations=sum(c.stage != Stage.COMPLETE for c in customers),
        at_risk=sum(c.risk == Risk.HIGH for c in customers),
        total_contract_value=sum((c.contract_value for c in customers), start=Decimal("0")),
        stage_counts=stage_counts,
    )
