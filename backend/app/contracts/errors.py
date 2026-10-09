"""Application과 API가 공유하는 안전한 오류 계약입니다. 원문 DB 오류를 보관하지 않습니다."""


class ApplicationError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    message = "처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."

    def __init__(self) -> None:
        super().__init__(self.message)


class PersistenceError(ApplicationError):
    pass


class DatabaseUnavailable(PersistenceError):
    code = "UPSTREAM_UNAVAILABLE"
    status_code = 503
    message = "일시적으로 데이터를 처리할 수 없습니다. 잠시 후 다시 시도해 주세요."


class IntegrityViolation(PersistenceError):
    code = "BUSINESS_RULE_VIOLATION"
    status_code = 422
    message = "다른 데이터와 충돌하는 내용이 있습니다. 입력 내용을 확인해 주세요."


class UniqueConflict(IntegrityViolation):
    message = "이미 등록된 내용이 있습니다. 중복 여부를 확인해 주세요."


class ForeignKeyConflict(IntegrityViolation):
    message = "연결된 데이터를 확인한 후 다시 시도해 주세요."


class ConcurrencyConflict(PersistenceError):
    code = "VERSION_CONFLICT"
    status_code = 409
    message = "다른 작업으로 데이터가 변경되었습니다. 새로 확인한 후 다시 시도해 주세요."


class ResourceLocked(PersistenceError):
    code = "RESOURCE_LOCKED"
    status_code = 409
    message = "다른 작업에서 데이터를 처리하고 있습니다. 잠시 후 다시 시도해 주세요."


class InvalidPersistenceValue(PersistenceError):
    code = "INVALID_INPUT"
    status_code = 422
    message = "입력값의 형식을 확인한 후 다시 시도해 주세요."
