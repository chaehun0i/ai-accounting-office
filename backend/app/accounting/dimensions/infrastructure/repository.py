from __future__ import annotations

from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.accounting.dimensions.domain.entities import Dimension, DimensionValue
from app.accounting.dimensions.infrastructure.models import DimensionModel, DimensionValueModel


class DimensionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_dimensions(self, company: UUID, *, lock: bool = False) -> list[Dimension]:
        query = (
            select(DimensionModel)
            .where(DimensionModel.company_id == company)
            .order_by(DimensionModel.id)
        )
        rows = self.session.scalars(query.with_for_update() if lock else query)
        return [
            Dimension(**{k: getattr(r, k) for k in Dimension.__dataclass_fields__}) for r in rows
        ]

    def get(self, company: UUID, resource: UUID, *, lock: bool = False) -> Dimension | None:
        query = select(DimensionModel).where(
            DimensionModel.company_id == company, DimensionModel.id == resource
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        return (
            Dimension(**{k: getattr(row, k) for k in Dimension.__dataclass_fields__})
            if row
            else None
        )

    def values(self, company: UUID, dimension: UUID, *, lock: bool = False) -> list[DimensionValue]:
        query = (
            select(DimensionValueModel)
            .where(
                DimensionValueModel.company_id == company,
                DimensionValueModel.dimension_id == dimension,
            )
            .order_by(DimensionValueModel.id)
        )
        rows = self.session.scalars(query.with_for_update() if lock else query)
        return [
            DimensionValue(**{k: getattr(r, k) for k in DimensionValue.__dataclass_fields__})
            for r in rows
        ]

    def add(self, value: Dimension | DimensionValue) -> None:
        model = DimensionModel if isinstance(value, Dimension) else DimensionValueModel
        self.session.add(model(**asdict(value)))
        self.session.flush()

    def update(self, value: Dimension | DimensionValue, expected_version: int) -> bool:
        model = DimensionModel if isinstance(value, Dimension) else DimensionValueModel
        result = self.session.execute(
            update(model)
            .where(
                model.company_id == value.company_id,
                model.id == value.id,
                model.version == expected_version,
            )
            .values(**asdict(value))
        )
        self.session.flush()
        return cast(CursorResult[object], result).rowcount == 1
