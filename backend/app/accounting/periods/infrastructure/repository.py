from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.periods.domain.entities import Period
from app.accounting.periods.infrastructure.models import PeriodModel


class PeriodRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def entity(row: PeriodModel) -> Period:
        return Period(**{k: getattr(row, k) for k in Period.__dataclass_fields__})

    def get(self, *, company_id: UUID, resource_id: UUID) -> Period | None:
        row = self.session.scalar(
            select(PeriodModel).where(
                PeriodModel.company_id == company_id, PeriodModel.id == resource_id
            )
        )
        return self.entity(row) if row else None

    def list(self, company_id: UUID) -> list[Period]:
        return [
            self.entity(row)
            for row in self.session.scalars(
                select(PeriodModel)
                .where(PeriodModel.company_id == company_id)
                .order_by(PeriodModel.start_date)
            )
        ]

    def add(self, value: Period) -> None:
        self.session.add(PeriodModel(**asdict(value)))
        self.session.flush()
