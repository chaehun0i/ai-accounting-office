"""해시는 API 직렬화와 별개이며 버전과 요청자·회사에 결합됩니다."""

import hashlib
import json
from dataclasses import asdict
from uuid import UUID

from app.intake.domain.canonical_fields import Mapping
from app.intake.domain.validation import CanonicalRow

PREVIEW_DEFINITION = "accounting-intake-1"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def preview_digest(
    company_id: UUID,
    requester: UUID,
    file_sha256: str,
    mapping_version: int,
    source_type: str,
    target_context: str,
    source_system: str,
    mappings: list[Mapping],
) -> str:
    return digest(
        {
            "definition": PREVIEW_DEFINITION,
            "company": str(company_id),
            "requester": str(requester),
            "file": file_sha256,
            "mapping_version": mapping_version,
            "source": source_type,
            "target": target_context,
            "system": source_system,
            "mapping": [
                asdict(m) for m in sorted(mappings, key=lambda m: (m.sheet_index, m.column_index))
            ],
        }
    )


def row_digest(row: CanonicalRow) -> str:
    return digest(dict(row.values))
