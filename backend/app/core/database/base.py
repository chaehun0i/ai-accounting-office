"""업무 컬럼이나 테이블을 소유하지 않는 SQLAlchemy 선언 기반입니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.core.database.naming import NAMING_CONVENTION
from app.core.database.types import MoneyNumeric, ResourceUUID, UTCDateTime


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {UUID: ResourceUUID(), Decimal: MoneyNumeric(), datetime: UTCDateTime()}
