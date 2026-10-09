from app.contracts.errors import ApplicationError


class AuthenticationRequired(ApplicationError):
    code = "AUTHENTICATION_REQUIRED"
    status_code = 401
    message = "로그인 정보를 확인한 후 다시 로그인해 주세요."


class AuthorizationDenied(ApplicationError):
    code = "AUTHORIZATION_DENIED"
    status_code = 403
    message = "이 작업을 수행할 권한이 없습니다. 회사 관리자에게 문의해 주세요."


class ResourceNotFound(ApplicationError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404
    message = "접근할 수 있는 정보를 찾지 못했습니다. 선택한 회사를 확인해 주세요."


class VersionConflict(ApplicationError):
    code = "VERSION_CONFLICT"
    status_code = 409
    message = "정보가 변경되었습니다. 새로 확인한 후 다시 시도해 주세요."


class StateConflict(ApplicationError):
    code = "STATE_TRANSITION_NOT_ALLOWED"
    status_code = 409
    message = "이미 처리되었거나 현재 사용할 수 없는 요청입니다."


class InvalidInput(ApplicationError):
    code = "INVALID_INPUT"
    status_code = 422
    message = "입력 내용을 확인해 주세요."


class RateLimited(ApplicationError):
    code = "RATE_LIMITED"
    status_code = 429
    message = "시도가 너무 많습니다. 잠시 후 다시 시도해 주세요."
