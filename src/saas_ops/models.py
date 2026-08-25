from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Stage(StrEnum):
    DISCOVERY = "discovery"
    DATA_VALIDATION = "data_validation"
    CONFIGURATION = "configuration"
    UAT = "uat"
    GO_LIVE = "go_live"
    HYPERCARE = "hypercare"
    COMPLETE = "complete"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner: str = Field(min_length=2, max_length=120)
    target_go_live: datetime
    contract_value: float = Field(ge=0)


class Customer(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stage: Stage
    risk: Risk
    created_at: datetime
    updated_at: datetime


class TransitionRequest(BaseModel):
    stage: Stage
    actor: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=500)


class AuditEvent(BaseModel):
    id: int
    customer_id: int
    actor: str
    action: str
    details: str
    created_at: datetime


class Dashboard(BaseModel):
    total_customers: int
    active_implementations: int
    at_risk: int
    total_contract_value: float
    stage_counts: dict[str, int]

