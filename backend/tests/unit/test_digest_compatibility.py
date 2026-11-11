import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.closing.domain.rules import stable_digest
from app.core.digests import value_digest


def test_typed_digest_preserves_journal_and_closing_fingerprints():
    value = {
        "description": "감가상각 검토",
        "amount": Decimal("123.4500"),
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "date": date(2026, 1, 31),
        "time": datetime(2026, 1, 31, tzinfo=UTC),
        "lines": ({"credit": Decimal("0.0000"), "optional": None},),
    }
    for sort_keys in (False, True):
        normalized = json.loads(json.dumps(value, default=str, sort_keys=sort_keys))
        expected = hashlib.sha256(
            json.dumps(
                normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        assert value_digest(value) == stable_digest(value) == expected
        assert value_digest(dict(reversed(list(value.items())))) == expected
    assert value_digest({**value, "amount": Decimal("123.45")}) != value_digest(value)
