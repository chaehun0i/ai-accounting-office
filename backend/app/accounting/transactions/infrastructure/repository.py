from dataclasses import asdict
from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.accounting.transactions.domain.entities import Transaction
from app.accounting.transactions.infrastructure.models import TransactionModel


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def entity(row: TransactionModel) -> Transaction:
        return Transaction(
            **{name: getattr(row, name) for name in Transaction.__dataclass_fields__}
        )

    def get(self, company_id: UUID, resource_id: UUID, *, lock: bool = False) -> Transaction | None:
        query = select(TransactionModel).where(
            TransactionModel.company_id == company_id, TransactionModel.id == resource_id
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        return self.entity(row) if row else None

    def source(self, company_id: UUID, system: str, source_id: str) -> Transaction | None:
        row = self.session.scalar(
            select(TransactionModel).where(
                TransactionModel.company_id == company_id,
                TransactionModel.source_system == system,
                TransactionModel.source_id == source_id,
            )
        )
        return self.entity(row) if row else None

    def list(self, company_id: UUID, date_from: date, date_to: date) -> list[Transaction]:
        return [
            self.entity(r)
            for r in self.session.scalars(
                select(TransactionModel)
                .where(
                    TransactionModel.company_id == company_id,
                    TransactionModel.accounting_date.between(date_from, date_to),
                )
                .order_by(TransactionModel.accounting_date, TransactionModel.id)
                .limit(500)
            )
        ]

    def add(self, value: Transaction) -> None:
        self.session.add(TransactionModel(**asdict(value)))
        self.session.flush()

    def update(self, value: Transaction, expected_version: int) -> bool:
        result = self.session.execute(
            update(TransactionModel)
            .where(
                TransactionModel.company_id == value.company_id,
                TransactionModel.id == value.id,
                TransactionModel.version == expected_version,
            )
            .values(**asdict(value))
        )
        return cast(CursorResult[object], result).rowcount == 1
