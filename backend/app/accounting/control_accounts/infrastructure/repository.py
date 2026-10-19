from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.control_accounts.infrastructure.models import (
    ControlAccountEventModel,
    ControlAccountMappingModel,
    ControlAccountRequestModel,
)
from app.companies.infrastructure.models import CompanyModel
from app.contracts.access_errors import ResourceNotFound, VersionConflict

if TYPE_CHECKING:
    from app.accounting.control_accounts.application.impact import ImpactAssessment

_REFERENCE_QUERIES = {
    "POSTED_JOURNAL": (
        "SELECT count(*) FROM journal_lines l JOIN journal_entries j "
        "ON j.company_id=l.company_id AND j.id=l.journal_entry_id "
        "WHERE l.company_id=:company AND l.account_id=:account AND j.status='POSTED'"
    ),
    "AR_REFERENCE": (
        "SELECT count(*) FROM receivables WHERE company_id=:company AND account_id=:account"
    ),
    "AP_REFERENCE": (
        "SELECT count(*) FROM payables WHERE company_id=:company AND account_id=:account"
    ),
    "BANK_REFERENCE": (
        "SELECT count(*) FROM bank_accounts "
        "WHERE company_id=:company AND control_account_id=:account"
    ),
    "CARD_REFERENCE": (
        "SELECT count(*) FROM card_accounts "
        "WHERE company_id=:company AND control_account_id=:account"
    ),
}


class ControlAccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_company(self, company_id: UUID) -> None:
        # Every mapping command starts with the same company lock. This also
        # serializes creation when no mapping row exists yet.
        row = self.session.scalar(
            select(CompanyModel.id).where(CompanyModel.id == company_id).with_for_update()
        )
        if row is None:
            raise ResourceNotFound()

    def mappings(self, company_id: UUID) -> list[ControlAccountMappingModel]:
        return list(
            self.session.scalars(
                select(ControlAccountMappingModel)
                .where(ControlAccountMappingModel.company_id == company_id)
                .order_by(ControlAccountMappingModel.role)
            )
        )

    def mapping(
        self, company_id: UUID, role: str, lock: bool = False
    ) -> ControlAccountMappingModel | None:
        query = select(ControlAccountMappingModel).where(
            ControlAccountMappingModel.company_id == company_id,
            ControlAccountMappingModel.role == role,
        )
        return self.session.scalar(query.with_for_update() if lock else query)

    def request(
        self, company_id: UUID, request_id: UUID, lock: bool = False
    ) -> ControlAccountRequestModel | None:
        query = select(ControlAccountRequestModel).where(
            ControlAccountRequestModel.company_id == company_id,
            ControlAccountRequestModel.id == request_id,
        )
        return self.session.scalar(query.with_for_update() if lock else query)

    def requests(self, company_id: UUID) -> list[ControlAccountRequestModel]:
        return list(
            self.session.scalars(
                select(ControlAccountRequestModel)
                .where(ControlAccountRequestModel.company_id == company_id)
                .order_by(ControlAccountRequestModel.created_at.desc())
            )
        )

    def request_by_key(
        self, company_id: UUID, requester_id: UUID, key: str
    ) -> ControlAccountRequestModel | None:
        return self.session.scalar(
            select(ControlAccountRequestModel).where(
                ControlAccountRequestModel.company_id == company_id,
                ControlAccountRequestModel.requester_id == requester_id,
                ControlAccountRequestModel.request_key == key,
            )
        )

    def impact(
        self,
        company_id: UUID,
        role: str,
        current_account_id: UUID | None,
        target_account_id: UUID,
    ) -> ImpactAssessment:
        from app.accounting.control_accounts.application.impact import assess_impact

        return assess_impact(self, company_id, role, current_account_id, target_account_id)

    def events(self, company_id: UUID, request_id: UUID) -> list[ControlAccountEventModel]:
        return list(
            self.session.scalars(
                select(ControlAccountEventModel)
                .where(
                    ControlAccountEventModel.company_id == company_id,
                    ControlAccountEventModel.request_id == request_id,
                )
                .order_by(ControlAccountEventModel.occurred_at, ControlAccountEventModel.id)
            )
        )

    def account(
        self, company_id: UUID, account_id: UUID, lock: bool = False
    ) -> AccountModel | None:
        query = select(AccountModel).where(
            AccountModel.company_id == company_id, AccountModel.id == account_id
        )
        return self.session.scalar(query.with_for_update() if lock else query)

    def add_request(self, **values: Any) -> ControlAccountRequestModel:
        row = ControlAccountRequestModel(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def add_event(self, **values: Any) -> None:
        self.session.add(ControlAccountEventModel(**values))
        self.session.flush()

    def reference_count(self, code: str, company_id: UUID, account_id: UUID) -> int:
        return int(
            self.session.scalar(
                text(_REFERENCE_QUERIES[code]), {"company": company_id, "account": account_id}
            )
            or 0
        )

    def set_mapping(
        self, company_id: UUID, role: str, target_account_id: UUID, expected_version: int
    ) -> ControlAccountMappingModel:
        current = self.mapping(company_id, role, lock=True)
        if current is None:
            if expected_version != 0:
                raise VersionConflict()
            current = ControlAccountMappingModel(
                id=uuid4(),
                company_id=company_id,
                role=role,
                account_id=target_account_id,
                version=1,
                updated_at=datetime.now(UTC),
            )
            self.session.add(current)
        else:
            if current.version != expected_version:
                raise VersionConflict()
            current.account_id = target_account_id
            current.version += 1
            current.updated_at = datetime.now(UTC)
        self.session.flush()
        return current
