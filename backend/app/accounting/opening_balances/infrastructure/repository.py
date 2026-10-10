from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.journals.domain.entities import Journal
from app.accounting.opening_balances.infrastructure.models import (
    OpeningImportModel,
    OpeningLineModel,
)


class OpeningRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def existing(self, company: UUID, session_id: UUID, version: int) -> UUID | None:
        return self.session.scalar(
            select(OpeningImportModel.journal_id).where(
                OpeningImportModel.company_id == company,
                OpeningImportModel.onboarding_session_id == session_id,
                OpeningImportModel.source_version == version,
            )
        )

    def add(
        self,
        journal: Journal,
        session_id: UUID,
        version: int,
        fingerprint: str,
        row_keys: tuple[str, ...],
        now: datetime,
    ) -> None:
        identifier = uuid4()
        self.session.add(
            OpeningImportModel(
                id=identifier,
                company_id=journal.company_id,
                onboarding_session_id=session_id,
                source_version=version,
                source_digest=fingerprint,
                as_of_date=journal.entry_date,
                journal_id=journal.id,
                created_by=journal.created_by,
                created_at=now,
            )
        )
        self.session.flush()
        for line, key in zip(journal.lines, row_keys, strict=True):
            self.session.add(
                OpeningLineModel(
                    id=uuid4(),
                    company_id=journal.company_id,
                    opening_balance_import_id=identifier,
                    source_row_key=key,
                    account_id=line.account_id,
                    counterparty_id=line.counterparty_id,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                )
            )
        self.session.flush()
