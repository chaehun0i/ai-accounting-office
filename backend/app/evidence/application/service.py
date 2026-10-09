from collections.abc import Callable
from dataclasses import replace
from uuid import UUID, uuid4

from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.evidence.application.contracts import EvidenceUnitOfWork
from app.evidence.domain.entities import Evidence
from app.evidence.domain.types import EvidenceType
from app.identity.users.domain.entities import Principal


class EvidenceService:
    def __init__(self, factory: Callable[[], EvidenceUnitOfWork]) -> None:
        self.factory = factory

    def get(self, actor: Principal, company_id: UUID, resource_id: UUID) -> Evidence:
        with self.factory() as uow:
            require_company(uow, actor, company_id, "evidence.read")
            value = uow.evidences.get(company_id=company_id, resource_id=resource_id)
            if value is None:
                raise ResourceNotFound()
            return value

    def derive(
        self,
        actor: Principal,
        company_id: UUID,
        parent_id: UUID,
        evidence_type: EvidenceType,
        source_id: UUID,
    ) -> Evidence:
        # 새 identity는 이미 존재하는 parent만 참조하므로 이 경로에서 순환을 만들 수 없습니다.
        with self.factory() as uow:
            require_company(uow, actor, company_id, "evidence.read")
            require_company(uow, actor, company_id, "evidence.upload")
            parent = uow.evidences.get(company_id=company_id, resource_id=parent_id)
            if parent is None:
                raise ResourceNotFound()
            now = uow.now()
            value = replace(
                parent,
                id=uuid4(),
                evidence_type=evidence_type,
                source_type="DERIVATION",
                source_id=str(source_id),
                parent_evidence_id=parent.id,
                created_by=actor.user_id,
                created_at=now,
                ingested_at=now,
            )
            uow.evidences.add(value)
            return value
