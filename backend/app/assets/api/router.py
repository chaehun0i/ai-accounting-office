from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.transactions.api.schemas import TransactionCreate
from app.assets.application.service import AssetService
from app.assets.domain.entities import FixedAsset
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["Fixed assets"])


def assets(container: Container) -> AssetService:
    if container.assets is None:
        raise DatabaseUnavailable()
    return container.assets


Service = Annotated[AssetService, Depends(assets)]


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_from: date
    proration: Literal["MONTHLY", "DAILY"]
    acquisition_month: Literal["FULL", "NEXT_MONTH"]


class PolicyRead(PolicyCreate):
    id: UUID
    company_id: UUID
    version: int
    created_by: UUID
    created_at: datetime


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    asset_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
    asset_name: str = Field(min_length=1, max_length=200)
    asset_class: str = Field(min_length=1, max_length=60)
    acquisition_date: date
    in_service_date: date
    acquisition_cost: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    residual_value: Decimal = Field(ge=0, max_digits=19, decimal_places=4)
    useful_life_months: int = Field(ge=1, le=1200)
    asset_account_id: UUID
    accumulated_account_id: UUID
    expense_account_id: UUID
    acquisition_journal_id: UUID

    @field_validator("acquisition_cost", "residual_value", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        return TransactionCreate.no_float(value)


class AssetRead(AssetCreate):
    id: UUID
    company_id: UUID
    depreciation_method: str
    status: str
    version: int
    created_by: UUID
    created_at: datetime


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID


class LineRead(BaseModel):
    id: UUID
    company_id: UUID
    depreciation_run_id: UUID
    fixed_asset_id: UUID
    opening_accumulated: Decimal
    current_depreciation: Decimal
    closing_accumulated: Decimal
    carrying_amount: Decimal
    proposed_journal_id: UUID | None


class RunRead(BaseModel):
    id: UUID
    company_id: UUID
    period_id: UUID
    policy_id: UUID
    policy_version: int
    status: str
    total_amount: Decimal
    created_by: UUID
    created_at: datetime
    lines: list[LineRead]


@router.get("/fixed-assets/policies", response_model=list[PolicyRead])
def policies(actor: Actor, company_id: CompanyScope, service: Service) -> list[PolicyRead]:
    return [PolicyRead.model_validate(asdict(v)) for v in service.policies(actor, company_id)]


@router.post("/fixed-assets/policies", response_model=PolicyRead, status_code=201, dependencies=[Depends(csrf)])
def create_policy(payload: PolicyCreate, actor: Actor, company_id: CompanyScope, service: Service) -> PolicyRead:
    return PolicyRead.model_validate(asdict(service.create_policy(actor, company_id, **payload.model_dump())))


@router.get("/fixed-assets", response_model=list[AssetRead])
def listing(actor: Actor, company_id: CompanyScope, service: Service) -> list[AssetRead]:
    return [AssetRead.model_validate(asdict(v)) for v in service.list_assets(actor, company_id)]


@router.post("/fixed-assets", response_model=AssetRead, status_code=201, dependencies=[Depends(csrf)])
def register(payload: AssetCreate, actor: Actor, company_id: CompanyScope, service: Service) -> AssetRead:
    value = FixedAsset(id=uuid4(), company_id=company_id, depreciation_method="STRAIGHT_LINE",
                       status="IN_SERVICE", version=1, created_by=actor.user_id,
                       created_at=datetime.now(UTC), **payload.model_dump())
    return AssetRead.model_validate(asdict(service.register(actor, value)))


@router.post("/depreciation-runs", response_model=RunRead, status_code=201, dependencies=[Depends(csrf)])
def calculate(payload: RunCreate, actor: Actor, company_id: CompanyScope, service: Service) -> RunRead:
    return RunRead.model_validate(asdict(service.calculate(actor, company_id, payload.period_id)))


@router.get("/depreciation-runs/{resource_id}", response_model=RunRead)
def get_run(resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> RunRead:
    return RunRead.model_validate(asdict(service.get_run(actor, company_id, resource_id)))
