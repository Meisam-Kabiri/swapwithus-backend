from datetime import date
from typing import Annotated, List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.image import ImageMetadataItem
from app.models.utils import snake_to_camel


class CaravanListingCreate(BaseModel):
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
    title: Annotated[str, Field(max_length=200, min_length=5)]
    vehicle_type: Literal["caravan", "campervan", "motorhome"]
    
    # Location (Required)
    country: Annotated[str, Field(max_length=100, min_length=2)]
    city: Annotated[str, Field(max_length=100, min_length=2)]
    
    # Capacity (Required)
    max_guests: Annotated[int, Field(gt=0, le=20)]
    
    # Exchange Details (Required)
    exchange_method: Literal["pickup_only", "delivery_possible", "both"]
    
    # Vehicle-type specific requirements
    tow_requirement: Annotated[str, Field(max_length=100)] | None = None  # For caravan
    drive_license_req: Annotated[str, Field(max_length=50)] | None = None  # For campervan/motorhome
    
    # Vehicle Details (optional but recommended)
    year: Annotated[int, Field(ge=1950, le=2100)] | None = None
    make: Annotated[str, Field(max_length=100)] | None = None
    model: Annotated[str, Field(max_length=100)] | None = None
    condition: Literal["new", "excellent", "good", "fair", "needs_work"] | None = None
    registration_country: Annotated[str, Field(max_length=100)] | None = None
    
    # For campervan/motorhome
    fuel_type: Literal["diesel", "petrol", "electric", "hybrid"] | None = None
    transmission: Literal["manual", "automatic"] | None = None
    mileage_km: Annotated[int, Field(ge=0)] | None = None
    
    # Dimensions & weight
    length_meters: Annotated[float, Field(gt=0, le=30)] | None = None
    weight_kg: Annotated[int, Field(gt=0)] | None = None
    
    # Sleeping Arrangements
    bed_layout: Annotated[str, Field(max_length=200)] | None = None
    bed_count: Annotated[int, Field(ge=0, le=20)] | None = None
    
    # Amenities & Features
    amenities: List[str] | None = Field(default_factory=list)  # toilet, shower, kitchenette, fridge, heating, AC, solar, awning, bikeRack, storageBoxes
    power_source: List[str] | None = Field(default_factory=list)  # battery, shore_power, solar, generator
    water_system: Annotated[str, Field(max_length=200)] | None = None  # e.g. "fresh_tank: 100L, grey_tank: 80L"
    winterized: bool | None = None
    
    # Rules & Policies
    pet_allowed: bool | None = None
    smoking_allowed: bool | None = None
    insurance_included: bool | None = None
    deposit_required: Annotated[int, Field(ge=0)] | None = None
    
    # Location & Availability
    location_note: Annotated[str, Field(max_length=500)] | None = None
    available_from: date | None = None
    available_until: date | None = None
    delivery_radius_km: Annotated[int, Field(ge=0)] | None = None
    
    # Description
    description: Annotated[str, Field(max_length=5000)] | None = None
    
    # Status (will default in DB)
    status: Literal["draft", "published", "archived"] | None = "draft"


class CaravanListingResponse(CaravanListingCreate):
    """Caravan listing with images for API responses"""
    images: List[ImageMetadataItem] | None = Field(default_factory=list)
