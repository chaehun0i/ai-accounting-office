from app.contracts.errors import ApplicationError


class InvalidValue(ApplicationError):
    code = "ONBOARDING_FIELD_INVALID"
    status_code = 422
    message = "입력값의 형식과 허용 범위를 확인해 주세요."


class NotReady(ApplicationError):
    code = "ONBOARDING_NOT_READY"
    status_code = 409
    message = (
        "필수 입력과 검증 결과를 확인해 주세요. 지원 준비 중인 자료는 아직 완료할 수 없습니다."
    )


class StaleDraft(ApplicationError):
    code = "ONBOARDING_IMPORT_STALE"
    status_code = 409
    message = "초안이 변경되었습니다. 최신 내용을 불러와 다시 검토해 주세요."


class TemplateUnsupported(ApplicationError):
    code = "ONBOARDING_TEMPLATE_UNSUPPORTED"
    status_code = 422
    message = "지원하는 온보딩 양식과 버전인지 확인해 주세요."
