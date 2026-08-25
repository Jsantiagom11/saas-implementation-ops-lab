from datetime import UTC, datetime
from sqlite3 import Row

from .database import connection
from .models import AuditEvent, Customer, CustomerCreate, Dashboard, Risk, Stage

STAGE_ORDER = list(Stage)


class CustomerNotFoundError(LookupError):
    pass


class InvalidTransitionError(ValueError):
    pass


def _customer(row: Row) -> Customer:
    return Customer(**dict(row))


def create_customer(payload: CustomerCreate) -> Customer:
    now = datetime.now(UTC).isoformat()
    with connection() as conn:
        cursor = conn.execute(
            """INSERT INTO customers
            (name, owner, target_go_live, contract_value, stage, risk, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.name, payload.owner, payload.target_go_live.isoformat(),
             payload.contract_value, Stage.DISCOVERY, Risk.LOW, now, now),
        )
        customer_id = int(cursor.lastrowid or 0)
        conn.execute(
            """INSERT INTO audit_events
            (customer_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)""",
            (customer_id, payload.owner, "customer.created", "Implementation opened", now),
        )
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    assert row is not None
    return _customer(row)


def list_customers() -> list[Customer]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM customers ORDER BY updated_at DESC").fetchall()
    return [_customer(row) for row in rows]


def transition(customer_id: int, stage: Stage, actor: str, note: str) -> Customer:
    now = datetime.now(UTC).isoformat()
    with connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise CustomerNotFoundError(customer_id)
        current = Stage(row["stage"])
        if STAGE_ORDER.index(stage) != STAGE_ORDER.index(current) + 1:
            raise InvalidTransitionError(f"Expected {STAGE_ORDER[STAGE_ORDER.index(current) + 1]}")
        stable_stages = {Stage.GO_LIVE, Stage.HYPERCARE, Stage.COMPLETE}
        risk = Risk.LOW if stage in stable_stages else row["risk"]
        conn.execute(
            "UPDATE customers SET stage = ?, risk = ?, updated_at = ? WHERE id = ?",
            (stage, risk, now, customer_id),
        )
        conn.execute(
            """INSERT INTO audit_events
            (customer_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)""",
            (customer_id, actor, "stage.transitioned", f"{current} -> {stage}: {note}", now),
        )
        updated = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    assert updated is not None
    return _customer(updated)


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
        total_contract_value=sum(c.contract_value for c in customers),
        stage_counts=stage_counts,
    )
