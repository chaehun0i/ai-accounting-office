import logging


def configure_logging() -> None:
    # 앱 로그에는 고정된 메시지와 서버가 생성한 요청 ID만 기록합니다.
    logger = logging.getLogger("accounting_office")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
