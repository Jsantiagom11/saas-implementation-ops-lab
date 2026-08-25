from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from .config import RiskThresholds
from .database import initialize
from .models import AuditEvent, Customer, CustomerCreate, Dashboard, TransitionRequest
from .service import (
    CustomerNotFoundError,
    InvalidTransitionError,
    audit_log,
    create_customer,
    dashboard,
    list_customers,
    transition,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    RiskThresholds.from_env()
    initialize()
    yield


app = FastAPI(title="SaaS Implementation Operations Lab", version="0.1.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("web/index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/customers", response_model=Customer, status_code=status.HTTP_201_CREATED)
def add_customer(payload: CustomerCreate) -> Customer:
    return create_customer(payload)


@app.get("/api/customers", response_model=list[Customer])
def customers() -> list[Customer]:
    return list_customers()


@app.post("/api/customers/{customer_id}/transition", response_model=Customer)
def move_customer(customer_id: int, payload: TransitionRequest) -> Customer:
    try:
        return transition(customer_id, payload.stage, payload.actor, payload.note)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Customer not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/customers/{customer_id}/audit", response_model=list[AuditEvent])
def customer_audit(customer_id: int) -> list[AuditEvent]:
    try:
        return audit_log(customer_id)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Customer not found") from exc


@app.get("/api/dashboard", response_model=Dashboard)
def dashboard_metrics() -> Dashboard:
    return dashboard()
