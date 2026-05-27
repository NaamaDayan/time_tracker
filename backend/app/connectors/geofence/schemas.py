from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeofenceEventIn(BaseModel):
    zone_name: str
    transition: Literal["ENTER", "EXIT"]
    lat: float
    lon: float
    timestamp: datetime
