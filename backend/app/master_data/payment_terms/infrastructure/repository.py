from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.master_data.payment_terms.domain.entities import PaymentTerm
from app.master_data.payment_terms.infrastructure.models import PaymentTermModel


class PaymentTermRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, company_id: UUID, resource_id: UUID) -> PaymentTerm | None:
        row = self.session.scalar(
            select(PaymentTermModel).where(
                PaymentTermModel.company_id == company_id, PaymentTermModel.id == resource_id
            )
        )
        return self.entity(row) if row else None

    def list(self, company_id: UUID) -> list[PaymentTerm]:
        return [
            self.entity(row)
            for row in self.session.scalars(
                select(PaymentTermModel)
                .where(PaymentTermModel.company_id == company_id)
                .order_by(PaymentTermModel.term_code)
            )
        ]

    def add(self, value: PaymentTerm) -> None:
        self.session.add(PaymentTermModel(**asdict(value)))
        self.session.flush()

    @staticmethod
    def entity(row: PaymentTermModel) -> PaymentTerm:
        return PaymentTerm(**{key: getattr(row, key) for key in PaymentTerm.__dataclass_fields__})
