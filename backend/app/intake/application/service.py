"""파일 I/O와 검증은 DB 잠금 밖에서, 최종 확정은 UoW 안에서 수행합니다."""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.companies.application.service import require_company
from app.contracts.access_errors import (
    AuthorizationDenied,
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal
from app.intake.application.contracts import IntakeUnitOfWork
from app.intake.domain.canonical_fields import SCHEMAS, Mapping, SourceType, TargetContext, suggest
from app.intake.domain.digest import digest, preview_digest, row_digest
from app.intake.domain.entities import Column, Import, Receipt
from app.intake.domain.errors import (
    IdempotencyConflict,
    MappingRequired,
    PreviewStale,
    SourceConflict,
)
from app.intake.domain.validation import CanonicalRow, ValidationError, validate
from app.intake.domain.workbook import Workbook
from app.storage.domain.contracts import ObjectStorage

PREVIEW_TTL_SECONDS = 900


@dataclass(frozen=True)
class Preview:
    import_id: UUID
    preview_digest: str
    version: int
    expires_at: datetime
    valid: bool
    row_count: int
    errors: list[ValidationError]
    rows: list[CanonicalRow]


class IntakeService:
    def __init__(
        self,
        factory: Callable[[], IntakeUnitOfWork],
        storage: ObjectStorage,
        parser: Callable[[str, bytes, str], Workbook],
    ) -> None:
        self.factory = factory
        self.storage = storage
        self.parser = parser

    def _get(
        self,
        uow: IntakeUnitOfWork,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        permission: str,
    ) -> Import:
        require_company(uow, actor, company, permission)
        value = uow.imports.get(company_id=company, resource_id=identifier)
        if value is None:
            raise ResourceNotFound()
        if value.requested_by != actor.user_id:
            raise AuthorizationDenied()
        return value

    def get(self, actor: Principal, company: UUID, identifier: UUID) -> Import:
        with self.factory() as uow:
            return self._get(uow, actor, company, identifier, "import.preview")

    def columns(self, actor: Principal, company: UUID, identifier: UUID) -> list[Column]:
        with self.factory() as uow:
            return uow.imports.columns(self._get(uow, actor, company, identifier, "import.preview"))

    def upload(
        self,
        actor: Principal,
        company: UUID,
        *,
        source: SourceType,
        target: TargetContext,
        source_system: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> Import:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", source_system):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "import.create")
            require_company(uow, actor, company, "evidence.upload")
        workbook = self.parser(filename, content, content_type)
        mappings = [
            m for sheet in workbook.sheets for m in suggest(source, sheet.index, sheet.headers)
        ]
        key = self.storage.put(company, content)
        try:
            with self.factory() as uow:
                require_company(uow, actor, company, "import.create")
                require_company(uow, actor, company, "evidence.upload")
                value = Import(
                    uuid4(),
                    company,
                    actor.user_id,
                    uuid4(),
                    key,
                    source,
                    target,
                    source_system,
                    filename,
                    content_type,
                    hashlib.sha256(content).hexdigest(),
                    "MAPPING_REQUIRED",
                    1,
                    1,
                    None,
                    None,
                    uow.now(),
                )
                uow.imports.add(value, workbook, mappings, len(content))
            return value
        except BaseException:
            self.storage.delete(company, key)
            raise

    def mapping(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        expected_version: int,
        mappings: list[Mapping],
    ) -> Import:
        with self.factory() as uow:
            value = self._get(uow, actor, company, identifier, "import.mapping.update")
            if value.status in {"COMPLETED", "CONFIRMED", "CANCELLED", "IMPORTING"}:
                raise StateConflict()
            if value.version != expected_version:
                raise VersionConflict()
            columns = uow.imports.columns(value)
            if {(m.sheet_index, m.column_index) for m in mappings} != {
                (c.sheet_index, c.column_index) for c in columns
            } or len(mappings) != len(columns):
                raise InvalidInput()
            valid_codes = {f.code for f in SCHEMAS[value.source_type]}
            used: set[tuple[int, str]] = set()
            for mapping in mappings:
                code = mapping.canonical_field_code
                if code is not None:
                    if code not in valid_codes or (mapping.sheet_index, code) in used:
                        raise InvalidInput()
                    used.add((mapping.sheet_index, code))
            confirmed = [
                Mapping(
                    m.sheet_index,
                    m.column_index,
                    m.canonical_field_code,
                    "USER_CONFIRMED" if m.canonical_field_code else "UNMAPPED",
                )
                for m in mappings
            ]
            uow.imports.map(value, confirmed, actor.user_id, uow.now())
            updated = uow.imports.get(company_id=company, resource_id=identifier)
            assert updated is not None
            return updated

    def _workbook(self, value: Import) -> Workbook:
        content = self.storage.read(value.company_id, value.storage_key)
        if hashlib.sha256(content).hexdigest() != value.file_sha256:
            raise PreviewStale()
        return self.parser(value.original_filename, content, value.content_type)

    @staticmethod
    def _digest(value: Import, mappings: list[Mapping]) -> str:
        return preview_digest(
            value.company_id,
            value.requested_by,
            value.file_sha256,
            value.mapping_version,
            value.source_type.value,
            value.target_context.value,
            value.source_system,
            mappings,
        )

    def preview(
        self, actor: Principal, company: UUID, identifier: UUID, expected_version: int
    ) -> Preview:
        value = self.get(actor, company, identifier)
        workbook = self._workbook(value)
        with self.factory() as uow:
            current = self._get(uow, actor, company, identifier, "import.preview")
            if current.version != expected_version or current.version != value.version:
                raise VersionConflict()
            if current.status in {"COMPLETED", "CONFIRMED", "CANCELLED", "IMPORTING"}:
                raise StateConflict()
            mappings = [c.mapping for c in uow.imports.columns(current)]
            records, errors = validate(workbook, current.source_type, mappings)
            signature = self._digest(current, mappings)
            now = uow.now()
            expires = now + timedelta(seconds=PREVIEW_TTL_SECONDS)
            uow.imports.preview(current, signature, expires, errors, now)
            # 표시할 대표 행만 응답하며 전체 행은 요청 종료 시 메모리에서 해제됩니다.
            samples = [
                CanonicalRow(
                    r.sheet_index,
                    r.row_number,
                    r.source_id,
                    tuple(
                        (
                            k,
                            v
                            if k
                            in {
                                "transaction_date",
                                "amount",
                                "currency",
                                "direction",
                                "account_code",
                            }
                            else "***",
                        )
                        for k, v in r.values
                    ),
                )
                for r in records[:5]
            ]
            return Preview(
                identifier,
                signature,
                current.version + 1,
                expires,
                not errors,
                sum(len(s.rows) for s in workbook.sheets),
                errors[:100],
                samples,
            )

    def confirm(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        *,
        expected_version: int,
        preview_digest: str,
        idempotency_key: str,
        confirmed: bool,
    ) -> Receipt:
        if not confirmed or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", idempotency_key):
            raise InvalidInput()
        fingerprint = digest([str(identifier), preview_digest, expected_version, confirmed])
        with self.factory() as uow:
            value = self._get(uow, actor, company, identifier, "import.confirm")
            replay = uow.imports.replay(company, actor.user_id, idempotency_key)
            if replay:
                if replay.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return replay.receipt
        workbook = self._workbook(value)
        with self.factory() as uow:
            current = self._get(uow, actor, company, identifier, "import.confirm")
            replay = uow.imports.replay(company, actor.user_id, idempotency_key)
            if replay:
                if replay.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return replay.receipt
            now = uow.now()
            mappings = [c.mapping for c in uow.imports.columns(current)]
            if (
                current.version != expected_version
                or current.version != value.version
                or current.preview_digest != preview_digest
                or self._digest(current, mappings) != preview_digest
                or current.preview_expires_at is None
                or current.preview_expires_at <= now
            ):
                raise PreviewStale()
            if current.status != "PREVIEW_READY":
                raise StateConflict()
            records, errors = validate(workbook, current.source_type, mappings)
            if errors or not records:
                raise MappingRequired()
            for record in records:
                existing = uow.imports.source(current, record.source_id)
                if existing is not None and existing != row_digest(record):
                    raise SourceConflict()
            result = Receipt(
                uuid4(),
                company,
                identifier,
                digest([row_digest(r) for r in sorted(records, key=lambda r: r.source_id)]),
                0,
                1,
                0,
                "COMPLETED",
                now,
            )
            uow.imports.confirm(
                current, result, records, actor.user_id, idempotency_key, fingerprint, now
            )
            return result

    def errors(self, actor: Principal, company: UUID, identifier: UUID) -> list[ValidationError]:
        with self.factory() as uow:
            return uow.imports.errors(self._get(uow, actor, company, identifier, "import.preview"))

    def receipt(self, actor: Principal, company: UUID, identifier: UUID) -> Receipt:
        with self.factory() as uow:
            self._get(uow, actor, company, identifier, "import.preview")
            result = uow.imports.receipt(company_id=company, import_id=identifier)
            if result is None:
                raise ResourceNotFound()
            return result
