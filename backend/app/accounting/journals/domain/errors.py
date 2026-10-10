"""회계 규칙 위반은 안전한 메시지와 안정적인 오류 코드로 전달합니다."""

from app.contracts.errors import ApplicationError


class AccountingError(ApplicationError):
    status_code = 422
    code = "BUSINESS_RULE_VIOLATION"
    message = "회계 입력 내용을 확인해 주세요."

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status
        super().__init__()
