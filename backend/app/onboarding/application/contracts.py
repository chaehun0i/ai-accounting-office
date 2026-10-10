from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.accounting.application.contracts import MasterUnitOfWork
from app.intake.application.contracts import Imports
from app.intake.domain.entities import Import
from app.onboarding.domain.entities import ImportLink, Receipt, Workspace
from app.onboarding.domain.validation import Issue
from app.onboarding.domain.values import Cell


class OnboardingRepository(Protocol):
    def get(self, *, company_id: UUID) -> Workspace | None: ...
    def start(self, company_id: UUID, actor: UUID, now: datetime) -> Workspace: ...
    def save(
        self,
        workspace: Workspace,
        cells: list[Cell],
        actor: UUID,
        now: datetime,
        source_import: UUID | None = None,
        status: str = "IN_PROGRESS",
    ) -> Workspace: ...
    def validation(self, workspace: Workspace, issues: list[Issue], now: datetime) -> None: ...
    def link(self, workspace: Workspace, value: Import, metadata: dict[str, str]) -> ImportLink: ...
    def import_link(self, company_id: UUID, import_id: UUID) -> ImportLink | None: ...
    def receipt(self, company_id: UUID, key: str, *, promotion: bool = False) -> Receipt | None: ...
    def record(
        self, workspace: Workspace, receipt: Receipt, key: str, *, promotion: bool = False
    ) -> None: ...


class OnboardingUnitOfWork(MasterUnitOfWork, Protocol):
    @property
    def onboarding(self) -> OnboardingRepository: ...
    @property
    def imports(self) -> Imports: ...
