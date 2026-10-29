"""현금흐름표 범위·분류 설정과 CLOSED 기간 사전 점검 API."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.cash_flow.entities import DisposalSource, NonCashDisclosure
from app.reporting.cash_flow.indirect import IndirectBridge
from app.reporting.cash_flow.service import CashFlowService
from app.reporting.cash_flow.snapshot import CashDrilldown, CashLine, CashStatement

router = APIRouter(prefix="/cash-flow", tags=["현금흐름표 사전 점검"])


def cash_flow(container: Container) -> CashFlowService:
    if container.cash_flow is None:
        raise DatabaseUnavailable()
    return container.cash_flow


Service = Annotated[CashFlowService, Depends(cash_flow)]


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_from: date
    interest_paid: Literal["OPERATING", "FINANCING"]
    interest_received: Literal["OPERATING", "INVESTING"]
    income_tax_paid: Literal["OPERATING", "INVESTING", "FINANCING"]


class PolicyRead(PolicyCreate):
    id: UUID
    version: int
    effective_to: date | None
    status: Literal["LATEST", "SUPERSEDED"]


@router.get("/policies", response_model=list[PolicyRead])
def policies(actor: Actor, company_id: CompanyScope, service: Service) -> list[PolicyRead]:
    return [PolicyRead.model_validate(asdict(item)) for item in service.policies(actor, company_id)]


@router.post("/policies", response_model=PolicyRead, status_code=201, dependencies=[Depends(csrf)])
def create_policy(
    payload: PolicyCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> PolicyRead:
    return PolicyRead.model_validate(
        asdict(service.create_policy(actor, company_id, **payload.model_dump()))
    )


class NonCashCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journal_id: UUID
    debit_line_id: UUID
    credit_line_id: UUID
    evidence_id: UUID
    source_type: Literal[
        "LEASE_IN_KIND", "EQUITY_CONTRIBUTION_IN_KIND", "DEBT_EQUITY_CONVERSION", "OTHER_VERIFIED"
    ]
    amount: Decimal


class DisposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journal_id: UUID
    cash_line_id: UUID
    asset_line_id: UUID
    gain_line_id: UUID
    evidence_id: UUID


@router.post(
    "/disposal-sources",
    response_model=DisposalSource,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def record_disposal_source(
    payload: DisposalCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> DisposalSource:
    return service.record_disposal_source(actor, company_id, **payload.model_dump())


@router.get("/disposal-sources", response_model=tuple[DisposalSource, ...])
def disposal_sources(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> tuple[DisposalSource, ...]:
    return service.disposal_sources(actor, company_id, period_id)


@router.post(
    "/non-cash-disclosures",
    response_model=NonCashDisclosure,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def record_non_cash_disclosure(
    payload: NonCashCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> NonCashDisclosure:
    return service.record_non_cash_disclosure(actor, company_id, **payload.model_dump())


@router.get("/non-cash-disclosures", response_model=tuple[NonCashDisclosure, ...])
def non_cash_disclosures(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> tuple[NonCashDisclosure, ...]:
    return service.non_cash_disclosures(actor, company_id, period_id)


class AdjustmentRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    adjustment_code: Literal[
        "OPERATING_RESULT", "NONCASH_PAIR", "WORKING_CAPITAL", "EXCLUDED_BALANCE", "DISPOSAL_GAIN"
    ]
    source_mapping_type: Literal["ACCOUNT_LEDGER", "ASSET_REGISTER", "INVENTORY_SUBLEDGER"]
    related_account_id: UUID | None = None
    effective_from: date
    effective_to: date | None = None
    policy_code: Literal["TAX_INTEREST_OPERATING"]
    policy_version: Literal[1]


class AdjustmentRuleRead(AdjustmentRuleCreate):
    id: UUID
    version: int


@router.get("/adjustment-rules", response_model=list[AdjustmentRuleRead])
def adjustment_rules(
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> list[AdjustmentRuleRead]:
    return [
        AdjustmentRuleRead.model_validate(asdict(row))
        for row in service.adjustment_rules(actor, company_id)
    ]


@router.post(
    "/adjustment-rules",
    response_model=AdjustmentRuleRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def map_adjustment(
    payload: AdjustmentRuleCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> AdjustmentRuleRead:
    return AdjustmentRuleRead.model_validate(
        asdict(service.map_adjustment(actor, company_id, **payload.model_dump()))
    )


@router.get("/indirect-bridge", response_model=IndirectBridge)
def indirect_bridge(
    period_id: UUID,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> IndirectBridge:
    return service.indirect_bridge(actor, company_id, period_id)


class CashScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    scope_type: Literal["CASH", "CASH_EQUIVALENT"]
    effective_from: date


class CashScopeRead(CashScopeCreate):
    id: UUID
    effective_to: date | None
    version: int


class ClassificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    activity_type: Literal["OPERATING", "INVESTING", "FINANCING", "EXCHANGE_EFFECT"]
    line_code: str
    effective_from: date


class ClassificationRead(ClassificationCreate):
    id: UUID
    effective_to: date | None
    version: int


class PreflightIssueRead(BaseModel):
    code: str
    journal_id: UUID | None


class PreflightRead(BaseModel):
    period_id: UUID
    close_version: int
    source_digest: str
    mapping_digest: str
    opening_cash: Decimal
    closing_cash: Decimal
    net_cash_movement: Decimal
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    exchange_effect: Decimal
    classified_journal_count: int
    issues: tuple[PreflightIssueRead, ...]
    ready: bool


class AllocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journal_id: UUID
    cash_line_id: UUID
    counterpart_line_id: UUID
    evidence_id: UUID
    amount: Decimal


class AllocationRead(AllocationCreate):
    id: UUID
    version: int
    replaces_id: UUID | None


class AllocationRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal
    evidence_id: UUID


class CashEventRead(BaseModel):
    journal_id: UUID
    cash_line_id: UUID
    cash_account_id: UUID
    counterpart_line_id: UUID
    counterpart_account_id: UUID
    activity_type: str
    line_code: str
    cash_inflow: Decimal
    cash_outflow: Decimal
    classification_id: UUID
    evidence_id: UUID | None


@router.get("/cash-scope", response_model=list[CashScopeRead])
def scopes(actor: Actor, company_id: CompanyScope, service: Service) -> list[CashScopeRead]:
    return [
        CashScopeRead.model_validate(asdict(item)) for item in service.scopes(actor, company_id)
    ]


@router.post(
    "/cash-scope", response_model=CashScopeRead, status_code=201, dependencies=[Depends(csrf)]
)
def map_cash(
    payload: CashScopeCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> CashScopeRead:
    return CashScopeRead.model_validate(
        asdict(service.map_cash(actor, company_id, **payload.model_dump()))
    )


@router.get("/classifications", response_model=list[ClassificationRead])
def classifications(
    actor: Actor, company_id: CompanyScope, service: Service
) -> list[ClassificationRead]:
    return [
        ClassificationRead.model_validate(asdict(item))
        for item in service.classifications(actor, company_id)
    ]


@router.post(
    "/classifications",
    response_model=ClassificationRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def map_activity(
    payload: ClassificationCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> ClassificationRead:
    return ClassificationRead.model_validate(
        asdict(service.map_activity(actor, company_id, **payload.model_dump()))
    )


@router.get("/preflight", response_model=PreflightRead)
def preflight(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> PreflightRead:
    return PreflightRead.model_validate(asdict(service.preflight(actor, company_id, period_id)))


@router.post(
    "/allocations", response_model=AllocationRead, status_code=201, dependencies=[Depends(csrf)]
)
def allocate(
    payload: AllocationCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> AllocationRead:
    return AllocationRead.model_validate(
        asdict(service.allocate(actor, company_id, **payload.model_dump()))
    )


@router.put(
    "/allocations/{allocation_id}",
    response_model=AllocationRead,
    dependencies=[Depends(csrf)],
)
def revise_allocation(
    allocation_id: UUID,
    payload: AllocationRevision,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> AllocationRead:
    return AllocationRead.model_validate(
        asdict(service.revise_allocation(actor, company_id, allocation_id, **payload.model_dump()))
    )


@router.get("/allocations", response_model=list[AllocationRead])
def allocation_history(
    journal_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[AllocationRead]:
    return [
        AllocationRead.model_validate(asdict(item))
        for item in service.allocation_history(actor, company_id, journal_id)
    ]


@router.get("/events", response_model=list[CashEventRead])
def events(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[CashEventRead]:
    return [
        CashEventRead.model_validate(asdict(item))
        for item in service.events(actor, company_id, period_id)
    ]


class SnapshotGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID
    statement_set_id: UUID
    close_version: int = Field(ge=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post(
    "/generate", response_model=CashStatement, status_code=201, dependencies=[Depends(csrf)]
)
def generate_snapshot(
    payload: SnapshotGenerate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> CashStatement:
    return service.generate_snapshot(actor, company_id, **payload.model_dump(), key=key)


@router.get("/statements", response_model=CashStatement)
def current_snapshot(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> CashStatement:
    return service.current_snapshot(actor, company_id, period_id)


@router.get("/{statement_id}", response_model=CashStatement)
def snapshot(
    statement_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> CashStatement:
    return service.snapshot(actor, company_id, statement_id)


@router.get("/{statement_id}/lines", response_model=tuple[CashLine, ...])
def snapshot_lines(
    statement_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> tuple[CashLine, ...]:
    return service.snapshot_lines(actor, company_id, statement_id)


@router.get("/{statement_id}/disclosures", response_model=tuple[NonCashDisclosure, ...])
def snapshot_disclosures(
    statement_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> tuple[NonCashDisclosure, ...]:
    return service.snapshot_disclosures(actor, company_id, statement_id)


@router.get("/{statement_id}/disposals", response_model=tuple[DisposalSource, ...])
def snapshot_disposals(
    statement_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> tuple[DisposalSource, ...]:
    return service.snapshot_disposals(actor, company_id, statement_id)


@router.get("/{statement_id}/drilldown", response_model=CashDrilldown)
def snapshot_drilldown(
    statement_id: UUID,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    line_id: UUID | None = None,
) -> CashDrilldown:
    return service.snapshot_drilldown(actor, company_id, statement_id, line_id)
