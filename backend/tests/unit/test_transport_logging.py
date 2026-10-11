"""HTTP 구현 교체 후에도 초대 capability를 출력하지 않습니다."""

import logging

import pytest

from app.core.logging import configure_logging


@pytest.mark.parametrize("name", ["httpx", "httpx2", "httpcore", "httpcore2"])
def test_transport_capability_is_masked(name, caplog):
    configure_logging()
    with caplog.at_level(logging.INFO, logger=name):
        logging.getLogger(name).info("POST /invitations/%s/accept", "sensitive-token")
    assert "sensitive-token" not in caplog.text
    assert "[숨김]" in caplog.text
