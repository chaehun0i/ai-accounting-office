from datetime import date
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.accounting.transactions.domain.entities import Transaction
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.accounting.transactions.infrastructure.repository import TransactionRepository
from app.core.database.base import Base
from app.tax.contracts import Period, Profile, Vat, Withholding
from app.tax.models import (
    TaxCommandModel,
    TaxPeriodModel,
    TaxProfileModel,
    VatModel,
    WithholdingModel,
)

T = TypeVar("T", bound=Base)
R = TypeVar("R", bound=BaseModel)


class TaxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock(self, company: UUID) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"tax:{company}"},
        )

    def add(self, row: T) -> T:
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, model: type[T], company: UUID, identifier: UUID) -> T | None:
        return self.session.scalar(
            select(model).where(model.company_id == company, model.id == identifier)  # type: ignore[attr-defined]
        )

    def command(self, company: UUID, actor: UUID, code: str, key: str) -> TaxCommandModel | None:
        return self.session.scalar(
            select(TaxCommandModel).where(
                TaxCommandModel.company_id == company,
                TaxCommandModel.actor_id == actor,
                TaxCommandModel.command_code == code,
                TaxCommandModel.idempotency_key == key,
            )
        )

    def profiles(self, company: UUID) -> tuple[Profile, ...]:
        return tuple(
            Profile.model_validate(row)
            for row in self.session.scalars(
                select(TaxProfileModel)
                .where(TaxProfileModel.company_id == company)
                .order_by(TaxProfileModel.effective_from, TaxProfileModel.id)
            )
        )

    def periods(self, company: UUID) -> tuple[Period, ...]:
        return tuple(
            Period.model_validate(row)
            for row in self.session.scalars(
                select(TaxPeriodModel)
                .where(TaxPeriodModel.company_id == company)
                .order_by(TaxPeriodModel.period_start, TaxPeriodModel.id)
            )
        )

    def facts(self, company: UUID) -> tuple[tuple[Vat, ...], tuple[Withholding, ...]]:
        return (
            self._latest(VatModel, Vat, company),
            self._latest(WithholdingModel, Withholding, company),
        )

    def _latest(self, model: type[T], result: type[R], company: UUID) -> tuple[R, ...]:
        # DISTINCT ON selects the latest immutable revision, including corrections to periods.
        query = (
            select(model)
            .where(model.company_id == company)
            .distinct(  # type: ignore[attr-defined]
                model.transaction_id  # type: ignore[attr-defined]
            )
            .order_by(model.transaction_id, model.revision.desc())
        )  # type: ignore[attr-defined]
        return tuple(result.model_validate(row) for row in self.session.scalars(query))

    def transactions(self, company: UUID, start: date, end: date) -> tuple[Transaction, ...]:
        return tuple(
            TransactionRepository.entity(row)
            for row in self.session.scalars(
                select(TransactionModel)
                .where(
                    TransactionModel.company_id == company,
                    TransactionModel.transaction_date.between(start, end),
                )
                .order_by(TransactionModel.id)
            )
        )
