from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounting.sequences.infrastructure.models import JournalSequenceModel
from app.contracts.access_errors import InvalidInput


class SequenceRepository:
    """호출한 Application/UoW가 커밋을 소유하며 번호 할당은 공개 API로 제공하지 않습니다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure(self, company_id: UUID, fiscal_year: int, sequence_key: str) -> None:
        if not (fiscal_year == 0 or 1900 <= fiscal_year <= 9998):
            raise InvalidInput()
        if not sequence_key or len(sequence_key) > 40:
            raise InvalidInput()
        self.session.execute(
            insert(JournalSequenceModel)
            .values(
                id=uuid4(),
                company_id=company_id,
                fiscal_year=fiscal_year,
                sequence_key=sequence_key,
                last_number=0,
            )
            .on_conflict_do_nothing(index_elements=["company_id", "fiscal_year", "sequence_key"])
        )

    def allocate(self, company_id: UUID, fiscal_year: int, sequence_key: str) -> int:
        self.ensure(company_id, fiscal_year, sequence_key)
        row = self.session.scalar(
            select(JournalSequenceModel)
            .where(
                JournalSequenceModel.company_id == company_id,
                JournalSequenceModel.fiscal_year == fiscal_year,
                JournalSequenceModel.sequence_key == sequence_key,
            )
            .with_for_update()
        )
        assert row is not None
        row.last_number += 1
        now = self.session.scalar(select(func.clock_timestamp()))
        assert now is not None
        row.updated_at = now
        self.session.flush()
        return row.last_number
