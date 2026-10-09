"""값 규칙을 PostgreSQL UUID·NUMERIC·TIMESTAMPTZ에 적용합니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric, Uuid
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.values import MONEY_PRECISION, MONEY_SCALE, as_utc, require_money, require_uuid


class ResourceUUID(TypeDecorator[UUID]):
    impl = Uuid
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(as_uuid=True, native_uuid=True)

    def process_bind_param(self, value: object, dialect: Dialect) -> UUID | None:
        return None if value is None else require_uuid(value)

    def process_result_value(self, value: object, dialect: Dialect) -> UUID | None:
        return None if value is None else require_uuid(value)


class MoneyNumeric(TypeDecorator[Decimal]):
    impl = Numeric
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(precision=MONEY_PRECISION, scale=MONEY_SCALE, asdecimal=True)

    def process_bind_param(self, value: object, dialect: Dialect) -> Decimal | None:
        return None if value is None else require_money(value)

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        return None if value is None else require_money(value)


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: object, dialect: Dialect) -> datetime | None:
        return None if value is None else as_utc(value)

    def process_result_value(self, value: object, dialect: Dialect) -> datetime | None:
        return None if value is None else as_utc(value)
