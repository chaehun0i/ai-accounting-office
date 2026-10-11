"""증빙 원문 대신 접근 검증된 출처 식별자만 제공합니다."""

from dataclasses import dataclass
from uuid import UUID

from app.accounting.transactions.application.service import TransactionService
from app.companies.application.service import require_company
from app.identity.users.domain.entities import Principal


@dataclass(frozen=True)
class EvidenceReferences:
    transaction_id: UUID
    import_id: UUID | None
    evidence_ids: tuple[UUID, ...]


class TransactionEvidenceQuery:
    def __init__(self, transactions: TransactionService):
        self.transactions = transactions

    def get(self, actor: Principal, company: UUID, resource: UUID) -> EvidenceReferences:
        source = self.transactions.get(actor, company, resource)
        with self.transactions.factory() as uow:
            require_company(uow, actor, company, "evidence.read")
        return EvidenceReferences(
            source.id, source.import_id, (source.evidence_id,) if source.evidence_id else ()
        )
