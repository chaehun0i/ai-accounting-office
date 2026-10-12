"""카드사 원천 상태를 명시적인 어휘로 정규화합니다."""

from app.contracts.access_errors import InvalidInput

STATUS_ALIASES = {
    "AUTHORIZED": "AUTHORIZED",
    "승인": "AUTHORIZED",
    "CAPTURED": "CAPTURED",
    "매입": "CAPTURED",
    "정산": "CAPTURED",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "취소": "CANCELLED",
    "REFUNDED": "REFUNDED",
    "환불": "REFUNDED",
    "REVERSED": "REVERSED",
    "승인취소": "REVERSED",
}


def normalize_status(value: str) -> str:
    result = STATUS_ALIASES.get(value.strip().upper())
    if result is None:
        raise InvalidInput()
    return result


def direction_for(status: str) -> str:
    # 카드 승인/매입은 지급수단 사실이며 비용 계정을 결정하지 않습니다.
    return "IN" if status == "REFUNDED" else "OUT"
