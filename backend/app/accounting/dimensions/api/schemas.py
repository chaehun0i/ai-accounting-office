from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DimensionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=200)
    dimension_type: Literal["BUSINESS_UNIT", "DEPARTMENT", "PROJECT", "COST_CENTER"]
    required_policy: Literal["OPTIONAL", "REQUIRED"] = "OPTIONAL"


class DimensionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    status: Literal["ACTIVE", "INACTIVE"]
    required_policy: Literal["OPTIONAL", "REQUIRED"]


class DimensionRead(DimensionCreate):
    id: UUID
    company_id: UUID
    status: Literal["ACTIVE", "INACTIVE"]
    version: int
    created_at: datetime
    updated_at: datetime


class ValueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=200)
    parent_value_id: UUID | None = None
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    effective_from: date | None = None
    effective_to: date | None = None


class ValueUpdate(ValueCreate):
    expected_version: int = Field(ge=1)


class ValueRead(ValueCreate):
    id: UUID
    company_id: UUID
    dimension_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime
