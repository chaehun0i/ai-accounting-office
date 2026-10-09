"""서버가 생성한 회사별 키만 허용하는 로컬 파일 저장소입니다."""

import re
from pathlib import Path
from uuid import UUID, uuid4

from app.contracts.access_errors import ResourceNotFound
from app.storage.domain.contracts import StorageUnavailable

MAX_FILE_BYTES = 2_000_000


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        # 생성 시 파일이나 디렉터리를 만들지 않습니다.
        self.root = root.resolve()

    def _path(self, company_id: UUID, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}/[0-9a-f]{32}", key):
            raise ResourceNotFound()
        if key.split("/")[0] != company_id.hex:
            raise ResourceNotFound()
        path = self.root / key
        if path.resolve() != path or not path.is_relative_to(self.root):
            raise ResourceNotFound()
        return path

    def put(self, company_id: UUID, content: bytes) -> str:
        if not content or len(content) > MAX_FILE_BYTES:
            raise StorageUnavailable()
        key = f"{company_id.hex}/{uuid4().hex}"
        path = self._path(company_id, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # 디렉터리 생성 후에도 링크를 다시 검사하고 기존 파일을 덮어쓰지 않습니다.
            path = self._path(company_id, key)
            with path.open("xb") as stream:
                stream.write(content)
        except OSError:
            path.unlink(missing_ok=True)
            raise StorageUnavailable() from None
        return key

    def read(self, company_id: UUID, key: str) -> bytes:
        path = self._path(company_id, key)
        try:
            with path.open("rb") as stream:
                value = stream.read(MAX_FILE_BYTES + 1)
            if len(value) > MAX_FILE_BYTES:
                raise StorageUnavailable()
            return value
        except FileNotFoundError:
            raise ResourceNotFound() from None
        except OSError:
            raise StorageUnavailable() from None

    def delete(self, company_id: UUID, key: str) -> None:
        try:
            self._path(company_id, key).unlink(missing_ok=True)
        except OSError:
            raise StorageUnavailable() from None

    def exists(self, company_id: UUID, key: str) -> bool:
        return self._path(company_id, key).is_file()
