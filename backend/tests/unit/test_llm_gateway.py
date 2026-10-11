"""외부 호출 없이 출력 계약·실패 안전성을 검사합니다."""

from uuid import uuid4

import pytest

from app.llm.contracts import AccountSelection, Classification, LLMError
from app.llm.gateway import LLMGateway
from app.llm.providers.fake import FakeProvider
from app.llm.providers.gemini import GeminiProvider


def test_fake_classification() -> None:
    value = LLMGateway(FakeProvider()).generate("classify", "{}", Classification)
    assert value.category == "OTHER"


def test_model_cannot_supply_accounting_numbers() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AccountSelection.model_validate(
            {"debit_account_id": uuid4(), "credit_account_id": uuid4(), "amount": "100"}
        )


def test_missing_key_is_safe() -> None:
    with pytest.raises(LLMError) as error:
        LLMGateway(GeminiProvider(None, "")).generate("classify", "{}", Classification)
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"
    assert "{}" not in str(error.value)


def test_timeout_retry_is_bounded() -> None:
    class TimeoutProvider(FakeProvider):
        attempts = 0

        def generate(self, *args, **kwargs):
            self.attempts += 1
            raise TimeoutError("민감한 provider 응답")

    provider = TimeoutProvider()
    with pytest.raises(LLMError) as error:
        LLMGateway(provider, max_retries=1).generate("classify", "{}", Classification)
    assert provider.attempts == 2
    assert error.value.code == "TIMEOUT"
    assert "민감한" not in str(error.value)


def test_invalid_output_fails_without_retry() -> None:
    class InvalidProvider(FakeProvider):
        def generate(self, *args, **kwargs):
            return Classification.model_construct(category="UNSUPPORTED", query_text="")

    with pytest.raises(LLMError) as error:
        LLMGateway(InvalidProvider()).generate("classify", "{}", Classification)
    assert error.value.code == "OUTPUT_SCHEMA_INVALID"
