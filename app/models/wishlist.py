from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.utils import snake_to_camel


class WishlistCreate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    category: Literal["homes", "books", "clothes", "caravans"]
    keywords: Annotated[list[Annotated[str, Field(min_length=1, max_length=50)]], Field(max_length=20)] = []
    filters: dict = Field(default_factory=dict)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, v: list[str]) -> list[str]:
        return [kw.strip().lower() for kw in v if kw.strip()]


class WishlistUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    keywords: Annotated[list[Annotated[str, Field(min_length=1, max_length=50)]], Field(max_length=20)] | None = None
    filters: dict | None = None
    status: Literal["active", "paused"] | None = None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [kw.strip().lower() for kw in v if kw.strip()]
