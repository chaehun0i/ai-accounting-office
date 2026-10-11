from app.contracts.access_errors import InvalidInput


class UnsupportedCurrency(InvalidInput):
    code = "FX_NOT_SUPPORTED"
    message = "현재 거래 생성은 원화 자료만 지원합니다. 파일의 통화를 확인해 주세요."
