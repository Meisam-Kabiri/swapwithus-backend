from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.utils import snake_to_camel


class SwapCreate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    user_b_uid: Annotated[str, Field(min_length=1, max_length=128)]
    listing_a_id: str  # UUID as string
    listing_b_id: str  # UUID as string
    listing_a_category: Annotated[str, Field(min_length=1, max_length=50)]
    listing_b_category: Annotated[str, Field(min_length=1, max_length=50)]
    conversation_id: str | None = None


class SwapUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    status: Literal["pending", "accepted", "completed", "cancelled"] | None = None
    cancellation_reason: Annotated[str, Field(max_length=500)] | None = None


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
