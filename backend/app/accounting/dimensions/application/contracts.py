from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.dimensions.domain.entities import Dimension, DimensionValue


class Dimensions(Protocol):
    def lock_scope(self, company: UUID) -> None: ...

    def list_dimensions(self, company: UUID, *, lock: bool = False) -> list[Dimension]: ...
    def get(self, company: UUID, resource: UUID, *, lock: bool = False) -> Dimension | None: ...
    def values(
        self, company: UUID, dimension: UUID, *, lock: bool = False
    ) -> list[DimensionValue]: ...
    def add(self, value: Dimension | DimensionValue) -> None: ...
    def update(self, value: Dimension | DimensionValue, expected_version: int) -> bool: ...


class DimensionUnitOfWork(MasterUnitOfWork, Protocol):
    @property
    def dimensions(self) -> Dimensions: ...
