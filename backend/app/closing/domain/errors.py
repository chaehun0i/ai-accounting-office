from app.contracts.errors import ApplicationError


class ClosingRunStale(ApplicationError):
    code = "CLOSING_RUN_STALE"
    status_code = 409
    message = "결산 기준 자료가 변경되었습니다. 검사를 다시 실행해 주세요."


class ClosingBlockersRemain(ApplicationError):
    code = "CLOSING_BLOCKERS_REMAIN"
    status_code = 409
    message = "결산 차단 항목을 해결한 뒤 다시 검사해 주세요."


class ClosingAdjustmentIncomplete(ApplicationError):
    code = "CLOSING_ADJUSTMENT_INCOMPLETE"
    status_code = 409
    message = "필수 결산조정 전표가 아직 기표되지 않았습니다."


class PeriodNotClosing(ApplicationError):
    code = "PERIOD_NOT_CLOSING"
    status_code = 409
    message = "결산 진행 중인 회계기간만 마감할 수 있습니다."


class PeriodAlreadyClosed(ApplicationError):
    code = "PERIOD_ALREADY_CLOSED"
    status_code = 409
    message = "이미 마감된 회계기간입니다."
