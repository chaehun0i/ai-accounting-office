from app.contracts.errors import ApplicationError


class IntakeFileError(ApplicationError):
    code = "WORKBOOK_INVALID"
    status_code = 422
    message = "파일 형식과 크기, 헤더를 확인해 주세요. 수식·매크로·외부 연결은 제거해 주세요."


class PreviewStale(ApplicationError):
    code = "PREVIEW_STALE"
    status_code = 409
    message = "미리보기가 만료되었거나 내용이 변경되었습니다. 다시 검증해 주세요."


class MappingRequired(ApplicationError):
    code = "MAPPING_REQUIRED"
    status_code = 422
    message = "필수 항목의 매핑과 오류를 확인한 후 다시 검증해 주세요."


class IdempotencyConflict(ApplicationError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409
    message = "같은 요청 번호에 다른 내용이 사용되었습니다. 요청 내용을 확인해 주세요."


class SourceConflict(ApplicationError):
    code = "IMPORT_SOURCE_CONFLICT"
    status_code = 409
    message = "이미 확정한 원본 자료와 내용이 다릅니다. 원본을 확인해 주세요."
