from typing import Annotated, List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.image import ImageMetadataItem
from app.models.utils import snake_to_camel


class BookListingCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    # Primary key (will be generated as UUID in backend)
    listing_id: UUID | None = None

    # Owner (Required)
    owner_firebase_uid: str
    # email: EmailStr | None = None
    # name: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    # profile_image: str | None = None

    # Book Details (Required)
    title: Annotated[str, Field(max_length=200, min_length=1)]
    author: Annotated[str, Field(max_length=200, min_length=1)]

    # Location (Required)
    city: Annotated[str, Field(max_length=100, min_length=2)]
    country: Annotated[str, Field(max_length=100, min_length=2)]

    # Exchange Details (Required)
    exchange_method: Literal["pickup_only", "shipping_possible", "both"]
    exchange_mode: Literal["permanent", "loan"]

    # Book Metadata (Required)
    language: Literal["en", "fr", "de", "es", "it", "sv", "no", "da", "fi", "is", "fa", "other"]
    format: Literal["paperback", "hardcover", "ebook", "audiobook"]

    # Optional fields
    condition: Literal["like_new", "good", "acceptable", "for_parts"] | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    publication_year: Annotated[int, Field(ge=1000, le=2100)] | None = None
    genre_tags: List[str] | None = Field(default_factory=list)

    # Status (will default in DB)
    # status: Literal["draft", "published", "archived"] | None = "draft"


class BookListingResponse(BookListingCreate):
    """Book listing with images for API responses"""
    images: List[ImageMetadataItem] | None = Field(default_factory=list)
