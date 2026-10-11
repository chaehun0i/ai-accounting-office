"""구조화 출력 재검증과 전체 호출 시간·재시도 상한을 소유합니다."""

from time import monotonic

from pydantic import ValidationError

from app.llm.contracts import LLMError, Provider, T


class LLMGateway:
    def __init__(self, provider: Provider, timeout_seconds: int = 30, max_retries: int = 1):
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def generate(self, task: str, facts: str, schema: type[T]) -> T:
        deadline = monotonic() + self.timeout_seconds
        for attempt in range(self.max_retries + 1):
            remaining = int(deadline - monotonic())
            if remaining < 1:
                raise LLMError("TIMEOUT")
            try:
                result = self.provider.generate(task, facts, schema, remaining)
                return schema.model_validate(result.model_dump())
            except ValidationError:
                raise LLMError("OUTPUT_SCHEMA_INVALID") from None
            except TimeoutError:
                error = LLMError("TIMEOUT")
            except LLMError as exc:
                error = exc
            if error.code not in {"TIMEOUT", "RATE_LIMITED", "PROVIDER_TEMPORARY"}:
                raise error from None
            if attempt == self.max_retries:
                raise error from None
        raise LLMError("PROVIDER_TEMPORARY")
