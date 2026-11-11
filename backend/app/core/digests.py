"""구조화된 값의 결정론적 SHA-256을 공통 경계에서 계산합니다."""

import hashlib
import json


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def value_digest(value: object) -> str:
    """Normalize typed values while preserving existing fingerprints."""
    return digest(json.loads(json.dumps(value, default=str)))
