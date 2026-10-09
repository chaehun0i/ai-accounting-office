"""원본 파일은 관계형 DB 밖에 보관하고 불변 키로 접근합니다."""

from typing import Protocol
from uuid import UUID

from app.contracts.errors import ApplicationError


class StorageUnavailable(ApplicationError):
    code = "STORAGE_UNAVAILABLE"
    status_code = 503
    message = "파일 저장소를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."


class ObjectStorage(Protocol):
    def put(self, company_id: UUID, content: bytes) -> str: ...
    def read(self, company_id: UUID, key: str) -> bytes: ...
    def delete(self, company_id: UUID, key: str) -> None: ...
    def exists(self, company_id: UUID, key: str) -> bool: ...
