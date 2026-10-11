"""원천 분개와 확정 배분으로 기준일별 보조부를 조회합니다."""

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalEvidenceModel, JournalModel
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.finance.payables.infrastructure.models import PayableModel
from app.finance.receivables.domain.entities import Obligation
from app.finance.receivables.infrastructure.models import ReceivableModel
from app.finance.settlements.domain.rules import target_status
from app.finance.settlements.infrastructure.models import (
    CollectionAllocationModel,
    CollectionModel,
    PaymentAllocationModel,
    PaymentModel,
)
from app.master_data.counterparties.infrastructure.models import CounterpartyModel


class ObligationRepository:
    def __init__(self, session: Session, kind: str) -> None:
        self.session = session
        self.model = ReceivableModel if kind == "AR" else PayableModel
        self.header = CollectionModel if kind == "AR" else PaymentModel
        self.allocation = CollectionAllocationModel if kind == "AR" else PaymentAllocationModel
        self.target_column = "receivable_id" if kind == "AR" else "payable_id"
        self.header_column = "collection_id" if kind == "AR" else "payment_id"
        self.date_column = "received_date" if kind == "AR" else "payment_date"

    def allocated(self, company: UUID, target: UUID, as_of: date) -> Decimal:
        return self.session.scalar(
            select(func.coalesce(func.sum(self.allocation.allocated_amount), 0))
            .join(self.header, getattr(self.allocation, self.header_column) == self.header.id)
            .where(
                self.allocation.company_id == company,
                self.header.company_id == company,
                getattr(self.allocation, self.target_column) == target,
                self.header.status != "DRAFT",
                getattr(self.header, self.date_column) <= as_of,
            )
        ) or Decimal("0")

    def _read(self, row: ReceivableModel | PayableModel, as_of: date) -> Obligation:
        journal = self.session.scalar(
            select(JournalModel).where(
                JournalModel.company_id == row.company_id, JournalModel.id == row.origin_journal_id
            )
        )
        assert journal is not None
        cp = self.session.scalar(
            select(CounterpartyModel).where(
                CounterpartyModel.company_id == row.company_id,
                CounterpartyModel.id == row.counterparty_id,
            )
        )
        assert cp is not None
        imported = (
            self.session.scalar(
                select(TransactionModel.import_id).where(
                    TransactionModel.company_id == row.company_id,
                    TransactionModel.id == journal.source_transaction_id,
                )
            )
            if journal.source_transaction_id
            else None
        )
        evidence = tuple(
            self.session.scalars(
                select(JournalEvidenceModel.evidence_id).where(
                    JournalEvidenceModel.company_id == row.company_id,
                    JournalEvidenceModel.journal_entry_id == journal.id,
                )
            )
        )
        paid = self.allocated(row.company_id, row.id, as_of)
        return Obligation(
            id=row.id,
            company_id=row.company_id,
            counterparty_id=row.counterparty_id,
            counterparty_name=cp.display_name,
            origin_journal_id=row.origin_journal_id,
            origin_line_no=row.origin_line_no,
            account_id=row.account_id,
            original_amount=row.original_amount,
            outstanding_amount=row.original_amount - paid,
            currency_code=row.currency_code,
            due_date=row.due_date,
            status=target_status(row.original_amount, paid),
            version=row.version,
            origin_date=journal.entry_date,
            source_transaction_id=journal.source_transaction_id,
            import_id=imported,
            evidence_ids=evidence,
        )

    def get(
        self, company_id: UUID, resource_id: UUID, as_of: date, *, lock: bool = False
    ) -> Obligation | None:
        query = select(self.model).where(
            self.model.company_id == company_id, self.model.id == resource_id
        )
        if lock:
            query = query.with_for_update()
        row = cast(ReceivableModel | PayableModel | None, self.session.scalar(query))
        return self._read(row, as_of) if row else None

    def list(self, company_id: UUID, as_of: date) -> list[Obligation]:
        rows = self.session.scalars(
            select(self.model)
            .join(
                JournalModel,
                (JournalModel.id == self.model.origin_journal_id)
                & (JournalModel.company_id == company_id),
            )
            .where(self.model.company_id == company_id, JournalModel.entry_date <= as_of)
            .order_by(self.model.due_date, self.model.id)
        )
        return [self._read(cast(ReceivableModel | PayableModel, row), as_of) for row in rows]

    def origin(self, company: UUID, journal: UUID, line_no: int) -> Obligation | None:
        row = cast(
            ReceivableModel | PayableModel | None,
            self.session.scalar(
                select(self.model)
                .where(
                    self.model.company_id == company,
                    self.model.origin_journal_id == journal,
                    self.model.origin_line_no == line_no,
                )
                .with_for_update()
            ),
        )
        return self._read(row, date.max) if row else None

    def add(
        self,
        company: UUID,
        journal: UUID,
        line_no: int,
        counterparty: UUID,
        account: UUID,
        amount: Decimal,
        due: date,
    ) -> UUID:
        resource = uuid4()
        self.session.add(
            self.model(
                id=resource,
                company_id=company,
                counterparty_id=counterparty,
                origin_journal_id=journal,
                origin_line_no=line_no,
                account_id=account,
                original_amount=amount,
                outstanding_amount=amount,
                currency_code="KRW",
                due_date=due,
                status="OPEN",
                version=1,
            )
        )
        self.session.flush()
        return resource

    def refresh(self, company: UUID, resource: UUID) -> None:
        row = cast(
            ReceivableModel | PayableModel | None,
            self.session.scalar(
                select(self.model)
                .where(self.model.company_id == company, self.model.id == resource)
                .with_for_update()
            ),
        )
        assert row is not None
        paid = self.allocated(company, resource, date.max)
        row.outstanding_amount = row.original_amount - paid
        row.status = target_status(row.original_amount, paid)
        row.version += 1
        from datetime import UTC, datetime

        row.updated_at = datetime.now(UTC)
        self.session.flush()
