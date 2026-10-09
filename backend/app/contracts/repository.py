"""업무 저장소의 최소 조회 계약입니다. 저장과 commit은 범용 CRUD로 추상화하지 않습니다."""

from typing import Protocol, TypeVar
from uuid import UUID

ResourceT = TypeVar("ResourceT", covariant=True)


class CompanyScopedRepository(Protocol[ResourceT]):
    def get(self, *, company_id: UUID, resource_id: UUID) -> ResourceT | None:
        """반드시 회사와 자원 ID를 함께 조회합니다. 전역 조회는 별도 Control Plane 계약입니다."""
        ...
