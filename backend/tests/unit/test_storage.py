from pathlib import Path
from uuid import uuid4

import pytest

from app.contracts.access_errors import ResourceNotFound
from app.storage.infrastructure.local import LocalObjectStorage


def test_storage_is_immutable_and_company_scoped(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    company = uuid4()
    first = storage.put(company, b"original")
    second = storage.put(company, b"original")
    assert first != second
    assert storage.read(company, first) == b"original"
    assert storage.exists(company, first)
    with pytest.raises(ResourceNotFound):
        storage.read(uuid4(), first)
    with pytest.raises(ResourceNotFound):
        storage.read(company, "../outside")
    storage.delete(company, first)
    assert not storage.exists(company, first)
    with pytest.raises(ResourceNotFound):
        storage.read(company, first)
