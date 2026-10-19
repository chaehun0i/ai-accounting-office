from app.contracts.errors import ApplicationError


class ControlAccountProtected(ApplicationError):
    code = "CONTROL_ACCOUNT_PROTECTED"
    status_code = 409
    message = "기존 회계 참조 또는 계정 정책으로 역할을 변경할 수 없습니다."


class ControlAccountIdempotencyConflict(ApplicationError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409
    message = "같은 멱등성 키에 다른 변경 내용이 등록되어 있습니다."
