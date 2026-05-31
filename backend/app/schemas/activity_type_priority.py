from pydantic import BaseModel, Field


class ActivityPriorityOut(BaseModel):
    slug: str
    rank: int
    display_name: str
    emoji: str
    color: str


class ActivityPriorityPutItem(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    rank: int = Field(ge=1)
