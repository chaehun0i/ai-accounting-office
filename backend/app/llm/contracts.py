"""Provider와 무관한 구조화 추론 계약입니다. 금액 계산을 위임하지 않습니다."""

from typing import Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.errors import ApplicationError

T = TypeVar("T", bound=BaseModel)


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Classification(StructuredModel):
    category: Literal["SALES", "PURCHASE", "EXPENSE", "OTHER"]
    query_text: str = Field(max_length=100)


class AccountSelection(StructuredModel):
    debit_account_id: UUID
    credit_account_id: UUID
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=20)


class AccountingQuestionRoute(StructuredModel):
    capability: Literal["CLOSING", "BALANCE_SHEET", "INCOME_STATEMENT", "UNSUPPORTED"]
    line_code: (
        Literal[
            "ASSETS",
            "LIABILITIES",
            "EQUITY",
            "REVENUE",
            "OPERATING_PROFIT",
            "NET_PROFIT",
        ]
        | None
    ) = None


class LLMError(ApplicationError):
    status_code = 503
    message = "제안을 만들 수 없습니다. 잠시 후 다시 시도해 주세요."

    def __init__(self, code: str) -> None:
        self.code = code
        self.message = "제안을 만들 수 없습니다. 잠시 후 다시 시도해 주세요."
        super().__init__()


class Provider(Protocol):
    code: str
    model: str

    def generate(self, task: str, facts: str, schema: type[T], timeout_seconds: int) -> T: ...
