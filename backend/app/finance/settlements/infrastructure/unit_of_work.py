from hashlib import sha256
from uuid import UUID

from sqlalchemy import text

from app.approvals.infrastructure.unit_of_work import AccountingSQLAlchemyUnitOfWork
from app.finance.receivables.infrastructure.repository import ObligationRepository
from app.finance.settlements.infrastructure.repository import SettlementRepository


class FinanceSQLAlchemyUnitOfWork(AccountingSQLAlchemyUnitOfWork):
    def obligations(self, kind: str) -> ObligationRepository:
        return ObligationRepository(self.session, kind)

    def settlements(self, kind: str) -> SettlementRepository:
        return SettlementRepository(self.session, kind)

    def lock_command(self, company: UUID, actor: UUID, command: str, key: str) -> None:
        # 없는 receipt 행도 같은 요청 지문 범위에서 직렬화합니다.
        number = int.from_bytes(
            sha256(f"{company}:{actor}:{command}:{key}".encode()).digest()[:8], signed=True
        )
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": number})
