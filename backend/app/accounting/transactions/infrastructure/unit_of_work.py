from typing import Self
from uuid import UUID

from sqlalchemy import select

from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.transactions.infrastructure.repository import TransactionRepository
from app.evidence.infrastructure.models import EvidenceModel
from app.intake.infrastructure.models import ImportModel


class TransactionSQLAlchemyUnitOfWork(MasterSQLAlchemyUnitOfWork):
    transactions: TransactionRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.transactions = TransactionRepository(self.session)
        return self

    def reference_exists(self, company_id: UUID, kind: str, resource_id: UUID) -> bool:
        model = EvidenceModel if kind == "evidence" else ImportModel
        return (
            self.session.scalar(
                select(model.id).where(model.company_id == company_id, model.id == resource_id)
            )
            is not None
        )

    def has_journal(self, company_id: UUID, transaction_id: UUID) -> bool:
        from app.accounting.journals.infrastructure.models import JournalModel

        return (
            self.session.scalar(
                select(JournalModel.id)
                .where(
                    JournalModel.company_id == company_id,
                    JournalModel.source_transaction_id == transaction_id,
                )
                .limit(1)
            )
            is not None
        )
