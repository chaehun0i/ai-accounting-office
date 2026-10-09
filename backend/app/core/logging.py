import logging
import re


class SensitivePathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # URL 기반 초대 capability는 HTTP 라이브러리와 access log에서도 숨깁니다.
        record.msg = re.sub(r"(/invitations/)[^/?\s]+(/accept)", r"\1[숨김]\2", record.getMessage())
        record.args = ()
        return True


def configure_logging() -> None:
    # 앱 로그에는 고정된 메시지와 서버가 생성한 요청 ID만 기록합니다.
    logger = logging.getLogger("accounting_office")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for name in ("uvicorn.access", "httpx"):
        transport = logging.getLogger(name)
        if not any(isinstance(item, SensitivePathFilter) for item in transport.filters):
            transport.addFilter(SensitivePathFilter())
