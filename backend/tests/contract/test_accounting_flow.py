"""회계 상태와 부정확한 금액 입력을 API 계약에서 거부합니다."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.accounting.journals.api.schemas import JournalCreate, JournalUpdate


def payload():
    return dict(
        accounting_period_id=uuid4(),
        entry_date=date(2026, 1, 1),
        description="계약 검증",
        lines=[
            dict(account_id=uuid4(), debit_amount="1"),
            dict(account_id=uuid4(), credit_amount="1"),
        ],
    )


def test_status_cannot_bypass_commands():
    with pytest.raises(ValidationError):
        JournalCreate(**payload(), status="POSTED")
    with pytest.raises(ValidationError):
        JournalUpdate(**payload(), expected_version=1, status="APPROVED")


def test_float_and_forged_opening_source_rejected():
    data = payload()
    data["lines"][0]["debit_amount"] = 0.1
    with pytest.raises(ValidationError):
        JournalCreate(**data)
    with pytest.raises(ValidationError):
        JournalCreate(**payload(), source_type="OPENING")
