"""수금·지급 헤더, 배분 행과 typed 멱등 영수증을 관리합니다."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.finance.settlements.domain.entities import Allocation, Settlement
from app.finance.settlements.infrastructure.models import (
    CollectionAllocationModel,
    CollectionModel,
    FinanceReceiptModel,
    PaymentAllocationModel,
    PaymentModel,
)
from app.intake.domain.errors import IdempotencyConflict


class SettlementRepository:
    def __init__(self, session: Session, kind: str) -> None:
        self.session = session
        self.kind = kind
        self.model = CollectionModel if kind == "AR" else PaymentModel
        self.line = CollectionAllocationModel if kind == "AR" else PaymentAllocationModel
        self.header_column = "collection_id" if kind == "AR" else "payment_id"
        self.target_column = "receivable_id" if kind == "AR" else "payable_id"
        self.date_column = "received_date" if kind == "AR" else "payment_date"

    def get(self, company_id: UUID, resource_id: UUID, *, lock: bool = False) -> Settlement | None:
        query = select(self.model).where(
            self.model.company_id == company_id, self.model.id == resource_id
        )
        if lock:
            query = query.with_for_update()
        row = cast(CollectionModel | PaymentModel | None, self.session.scalar(query))
        if row is None:
            return None
        lines = tuple(
            Allocation(
                target_id=getattr(line, self.target_column),
                allocated_amount=cast(
                    CollectionAllocationModel | PaymentAllocationModel, line
                ).allocated_amount,
                expected_version=cast(
                    CollectionAllocationModel | PaymentAllocationModel, line
                ).expected_version,
            )
            for line in self.session.scalars(
                select(self.line)
                .where(
                    self.line.company_id == company_id,
                    getattr(self.line, self.header_column) == resource_id,
                )
                .order_by(getattr(self.line, self.target_column))
            )
        )
        return Settlement(
            id=row.id,
            company_id=company_id,
            journal_entry_id=row.journal_entry_id,
            settlement_date=getattr(row, self.date_column),
            total_amount=row.total_amount,
            currency_code=row.currency_code,
            method=row.method,
            reference_no=row.reference_no,
            status=row.status,
            version=row.version,
            unapplied_amount=row.total_amount
            - sum(
                (line.allocated_amount for line in lines),
                Decimal("0"),
            ),
            allocations=lines,
        )

    def list(self, company: UUID, target: UUID | None = None) -> list[Settlement]:
        query = select(self.model.id).where(self.model.company_id == company)
        if target:
            query = query.join(
                self.line, getattr(self.line, self.header_column) == self.model.id
            ).where(
                self.line.company_id == company, getattr(self.line, self.target_column) == target
            )
        ids = self.session.scalars(query.order_by(self.model.created_at, self.model.id))
        return [value for resource in ids if (value := self.get(company, resource)) is not None]

    def add(self, value: Settlement, actor: UUID) -> None:
        self.session.add(
            self.model(
                id=value.id,
                company_id=value.company_id,
                journal_entry_id=value.journal_entry_id,
                **{self.date_column: value.settlement_date},
                total_amount=value.total_amount,
                currency_code=value.currency_code,
                method=value.method,
                reference_no=value.reference_no,
                status="DRAFT",
                version=1,
                created_by=actor,
            )
        )
        self.session.flush()

    def replace_allocations(self, value: Settlement, lines: tuple[Allocation, ...]) -> None:
        self.session.execute(
            delete(self.line).where(
                self.line.company_id == value.company_id,
                getattr(self.line, self.header_column) == value.id,
            )
        )
        now = datetime.now(UTC)
        for line in lines:
            self.session.add(
                self.line(
                    id=uuid4(),
                    company_id=value.company_id,
                    **{self.header_column: value.id, self.target_column: line.target_id},
                    allocated_amount=line.allocated_amount,
                    expected_version=line.expected_version,
                    created_at=now,
                )
            )
        row = cast(
            CollectionModel | PaymentModel | None,
            self.session.scalar(
                select(self.model).where(
                    self.model.company_id == value.company_id, self.model.id == value.id
                )
            ),
        )
        assert row is not None
        row.version += 1
        row.updated_at = now
        self.session.flush()

    def confirm(self, value: Settlement) -> None:
        row = cast(
            CollectionModel | PaymentModel | None,
            self.session.scalar(
                select(self.model).where(
                    self.model.company_id == value.company_id, self.model.id == value.id
                )
            ),
        )
        assert row is not None
        row.status = "UNAPPLIED" if value.unapplied_amount > 0 else "CONFIRMED"
        row.confirmed_at = row.updated_at = datetime.now(UTC)
        row.version += 1
        self.session.flush()

    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None:
        row = self.session.scalar(
            select(FinanceReceiptModel).where(
                FinanceReceiptModel.company_id == company,
                FinanceReceiptModel.actor_id == actor,
                FinanceReceiptModel.command_code == command,
                FinanceReceiptModel.idempotency_key == key,
            )
        )
        if row and row.request_fingerprint != fingerprint:
            raise IdempotencyConflict()
        return row.collection_id or row.payment_id if row else None

    def receipt(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        value: Settlement,
    ) -> None:
        self.session.add(
            FinanceReceiptModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                command_code=command,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                **{self.header_column: value.id},
                result_version=value.version,
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()
