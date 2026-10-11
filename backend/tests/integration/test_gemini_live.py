"""실 Provider 호출은 명시적 환경 설정이 있는 경우에만 실행합니다."""

import os

import pytest

from app.llm.contracts import Classification
from app.llm.gateway import LLMGateway
from app.llm.providers.gemini import GeminiProvider


@pytest.mark.gemini
@pytest.mark.skipif(os.getenv("RUN_GEMINI_INTEGRATION") != "1", reason="Gemini 실 호출 opt-in 없음")
def test_opt_in_gemini_structured_output():
    key, model = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL", "")
    assert key and model, "실 호출 검증용 키와 모델을 환경변수로 지정해 주세요."
    result = LLMGateway(GeminiProvider(key, model), max_retries=0).generate(
        "classify", '{"source_type":"MANUAL","direction":"INFLOW"}', Classification
    )
    assert result.category in {"SALES", "PURCHASE", "EXPENSE", "OTHER"}
