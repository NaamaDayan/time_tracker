import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ZoneCategoryLiteral = Literal[
    "home", "work", "gym", "family", "social", "transit", "other"
]


class GpsZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: ZoneCategoryLiteral
    lat: float
    lon: float
    radius_meters: int = Field(default=150, ge=50, le=500)
    activity_type_slug: str | None = None


class GpsZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: ZoneCategoryLiteral | None = None
    lat: float | None = None
    lon: float | None = None
    radius_meters: int | None = Field(default=None, ge=50, le=500)
    activity_type_slug: str | None = None
    enabled: bool | None = None


class GpsZoneOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    activity_type_slug: str | None
    lat: float
    lon: float
    radius_meters: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
