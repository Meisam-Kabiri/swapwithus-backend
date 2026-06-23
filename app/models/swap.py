from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import LISTING_CATEGORIES
from app.models.utils import snake_to_camel


class SwapCreate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    # The requester offers their own listing (my_*) for the one they want
    # (their_*). The other party is NOT sent by the client - it's derived
    # server-side from their_listing's owner. The client only knows the listing
    # it's looking at, and must not need (or be trusted with) a uid.
    my_listing_id: str  # UUID as string - the one I give
    their_listing_id: str  # UUID as string - the one I want
    my_listing_category: str
    their_listing_category: str
    conversation_id: str | None = None

    @field_validator("my_listing_category", "their_listing_category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in LISTING_CATEGORIES:
            raise ValueError(f"category must be one of {LISTING_CATEGORIES}")
        return v


class SwapUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    status: Literal["pending", "accepted", "completed", "cancelled"] | None = None
    cancellation_reason: Annotated[str, Field(max_length=500)] | None = None


class SwapLegInput(BaseModel):
    """One leg of a proposed chain: from_user gives listing_id to to_user."""
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    from_user: Annotated[str, Field(min_length=1, max_length=128)]
    to_user: Annotated[str, Field(min_length=1, max_length=128)]
    listing_id: str
    category: str

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in LISTING_CATEGORIES:
            raise ValueError(f"category must be one of {LISTING_CATEGORIES}")
        return v


class ChainProposeRequest(BaseModel):
    """Materialise a suggested swap chain (2+ legs) into a real pending chain."""
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    legs: Annotated[list[SwapLegInput], Field(min_length=2, max_length=3)]
    conversation_id: str | None = None


# class SwapResponse(BaseModel):
#     model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

#     swap_id: str
#     created_at: str
#     updated_at: str

#     user_a_uid: str
#     user_b_uid: str

#     listing_a_id: str
#     listing_b_id: str
#     listing_a_category: str | None = None
#     listing_b_category: str | None = None

#     status: str
#     conversation_id: str | None = None

#     user_a_confirmed: bool
#     user_b_confirmed: bool
#     completed_at: str | None = None

#     initiated_at: str
#     accepted_at: str | None = None
#     cancelled_at: str | None = None

#     cancelled_by: str | None = None
#     cancellation_reason: str | None = None


class ReviewCreate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    swap_id: str
    reviewee_uid: Annotated[str, Field(min_length=1, max_length=128)]
    rating: Annotated[int, Field(ge=1, le=5)]
    communication_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    item_condition_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    timeliness_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    comment: Annotated[str, Field(max_length=500)] | None = None


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    rating: Annotated[int, Field(ge=1, le=5)] | None = None
    communication_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    item_condition_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    timeliness_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    comment: Annotated[str, Field(max_length=500)] | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    review_id: str
    created_at: str
    updated_at: str

    reviewer_uid: str
    reviewee_uid: str
    swap_id: str

    rating: int
    communication_rating: int | None = None
    item_condition_rating: int | None = None
    timeliness_rating: int | None = None
    comment: str | None = None


class UserStatsResponse(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    total_reviews: int
    average_rating: float
    total_swaps_completed: int
    trust_score: int
