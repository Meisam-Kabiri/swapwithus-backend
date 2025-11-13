from datetime import date
from typing import Annotated, Any, Dict, List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.image import ImageMetadataItem
from app.models.utils import snake_to_camel


class CarDetails(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True
    )

    make_model_year: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    connector_type: str | None = None
    seats: Annotated[int, Field(ge=1, le=20)] | None = None
    insurance_status: str | None = None
    min_driver_age: Annotated[int, Field(ge=16, le=99)] | None = None
    mileage_limit: Annotated[int, Field(ge=0)] | None = None
    pickup_note: str | None = None


class HomeListingCreate(BaseModel):
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

    # Step 1: Property Type (Optional)
    accommodation_type: Literal["entire_place", "private_room"]
    property_type: Literal[
        "apartment",
        "detached_house",
        "terrace_house",
        "duplex",
        "studio",
        "cottage",
        "loft",
        "cabin",
        "other",
    ]

    # Step 2: Capacity & Layout (Optional except max_guests)
    max_guests: Annotated[int, Field(gt=0, le=50)]
    bedrooms: Annotated[int, Field(ge=0, le=50)] | None = None
    size_m2: Annotated[float, Field(gt=0, le=100000)] | None = None
    surroundings_type: Annotated[str, Field(max_length=30)] | None = None

    # Step 3: Location (Required: country, city; Optional: rest)
    country: Annotated[str, Field(max_length=100, min_length=2)]
    city: Annotated[str, Field(max_length=100, min_length=2)]
    street_address: Annotated[str, Field(max_length=200, min_length=2)] | None = None
    postal_code: Annotated[str, Field(max_length=20, min_length=2)] | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    privacy_radius: Annotated[int, Field(ge=0)] | None = 500

    # Step 5: House Rules
    house_rules: List[str] | None = Field(default_factory=list)
    main_residence: bool | None = None

    # Step 6: Transport & Car Swap
    open_to_car_swap: bool = False
    require_car_swap_match: bool = False
    car_details: CarDetails | None = None


    # Step 7:  Available Amenities
    amenities: Dict[str, Any] | None = Field(default_factory=dict)
    accessibility_features: List[str] | None = Field(default_factory=list)
    parking_type: Literal["none", "street", "driveway", "garage", "covered"] | None = None

    # Step 8: Availability
    is_flexible: bool | None = None
    available_from: date | None = None
    available_until: date | None = None

    # Step 9: Title and Description (Required: title; Optional: description)
    title: Annotated[str, Field(max_length=200, min_length=5)]
    description: Annotated[str, Field(max_length=5000, min_length=10)] | None = None

    # Status (will default in DB)
    status: Literal["draft", "published", "archived"] | None = "draft"


class HomeListingResponse(HomeListingCreate):
    """Home listing with images for API responses"""
    images: List[ImageMetadataItem] | None = Field(default_factory=list)


#  validators for:

#   a) Coordinates validation:
#   from pydantic import model_validator

#   @model_validator(mode='after')
#   def validate_coordinates(self):
#       """Both lat and lng must be present or both absent"""
#       has_lat = self.latitude is not None
#       has_lng = self.longitude is not None
#       if has_lat != has_lng:
#           raise ValueError("Provide both latitude and longitude, or neither")
#       return self

#   b) Date validation:
#   @model_validator(mode='after')
#   def validate_dates(self):
#       """End date must be after start date"""
#       if (self.available_from and self.available_until and
#           self.available_until < self.available_from):
#           raise ValueError("available_until must be on or after available_from")
#       return self

#   c) Car swap logic:
#   @model_validator(mode='after')
#   def validate_car_swap(self):
#       """Cannot require car swap if not open to it"""
#       if self.require_car_swap_match and not self.open_to_car_swap:
#           raise ValueError("Cannot require car swap match without being open to car swap")
#       return self
