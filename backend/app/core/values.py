"""DB에 의존하지 않는 UUID·금액·UTC 값 규칙입니다."""

from datetime import UTC, datetime
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

MONEY_PRECISION = 19
MONEY_SCALE = 4
MONEY_QUANTUM = Decimal("0.0001")
MONEY_LIMIT = Decimal("1000000000000000")


def new_uuid() -> UUID:
    """Application에서 자원을 생성할 때 UUID를 발급합니다. DB 기본값은 사용하지 않습니다."""
    return uuid4()


def require_uuid(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError("식별자는 문자열 대신 UUID 값으로 전달해 주세요.")
    return value


def require_money(value: object) -> Decimal:
    """반올림 없이 NUMERIC(19,4)에 정확히 저장할 수 있는 Decimal만 허용합니다."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("금액은 유한한 Decimal 값으로 전달해 주세요.")
    if value.copy_abs() >= MONEY_LIMIT:
        raise ValueError("금액이 저장 가능한 범위를 벗어났습니다.")
    with localcontext() as context:
        context.prec = max(MONEY_PRECISION, len(value.as_tuple().digits))
        if value != value.quantize(MONEY_QUANTUM):
            raise ValueError("금액의 소수점 자릿수는 네 자리까지 사용할 수 있습니다.")
    return value


def as_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("시간대 정보가 포함된 날짜와 시간을 전달해 주세요.")
    return value.astimezone(UTC)
