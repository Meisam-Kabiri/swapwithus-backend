from typing import Annotated, List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.image import ImageMetadataItem
from app.models.utils import snake_to_camel


class ClothingListingCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    # Primary key (will be generated as UUID in backend)
    listing_id: UUID | None = None

    # Owner (Required)
    owner_firebase_uid: str
    email: EmailStr | None = None
    name: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    profile_image: str | None = None

    # Basic Info (Required)
    title: Annotated[str, Field(max_length=200, min_length=1)]
    clothing_category: Literal[
        "tshirt",
        "shirt",
        "dress",
        "trousers",
        "jeans",
        "coat",
        "jacket",
        "sweater",
        "hoodie",
        "sportswear",
        "shoes",
        "bag",
        "accessory",
        "other"
    ]
    size: Annotated[str, Field(max_length=20)]  # Free text: S, M, 38, etc.
    condition: Literal["new", "like_new", "very_good", "good", "used"]

    # Location (Required)
    city: Annotated[str, Field(max_length=100, min_length=2)]
    country: Annotated[str, Field(max_length=100, min_length=2)]

    # Exchange Details (Required)
    exchange_method: Literal["pickup_only", "shipping_possible", "both"]

    # Optional Clothing Details
    gender: Literal["women", "men", "unisex", "kids"] | None = None
    brand: Annotated[str, Field(max_length=100)] | None = None
    color: Annotated[str, Field(max_length=50)] | None = None
    material: Annotated[str, Field(max_length=200)] | None = None
    season: Literal["all", "spring", "summer", "autumn", "winter"] | None = None
    kids_age_range: Annotated[str, Field(max_length=50)] | None = None
    fit: Literal["regular", "oversized", "slim"] | None = None
    defects: Annotated[str, Field(max_length=500)] | None = None

    # Description
    description: Annotated[str, Field(max_length=5000)] | None = None

    # Status (will default in DB)
    status: Literal["draft", "published", "archived"] | None = "draft"


class ClothingListingResponse(ClothingListingCreate):
    """Clothing listing with images for API responses"""
    images: List[ImageMetadataItem] | None = Field(default_factory=list)
