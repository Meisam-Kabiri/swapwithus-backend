from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any, Annotated, Literal
from datetime import date
from uuid import UUID


def snake_to_camel(snake_str: str) -> str:
    first, *rest = snake_str.split("_")
    return first + "".join(x.title() for x in rest)


class HomeListingCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )

    # Primary key (will be generated as UUID in backend)
    listing_id: Optional[UUID] = None

    # Owner (Required)
    owner_firebase_uid: str
    email: Optional[EmailStr] = None
    name: Optional[Annotated[str, Field(max_length=100, min_length=2)]] = None
    profile_image: Optional[str] = None

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
    bedrooms: Optional[Annotated[int, Field(ge=0, le=50)]] = None

    size_input: Optional[str] = None
    size_unit: Optional[str] = None
    size_m2: Optional[int] = None
    surroundings_type: Optional[Annotated[str, Field(max_length=30)]] = None

    # Step 3: Location (Required: country, city; Optional: rest)
    country: Annotated[str, Field(max_length=100, min_length=2)]
    city: Annotated[str, Field(max_length=100, min_length=2)]
    street_address: Optional[Annotated[str, Field(max_length=200, min_length=2)]] = None
    postal_code: Optional[Annotated[str, Field(max_length=20, min_length=2)]] = None
    latitude: Optional[Annotated[float, Field(ge=-90, le=90)]] = None
    longitude: Optional[Annotated[float, Field(ge=-180, le=180)]] = None
    privacy_radius: Optional[Annotated[int, Field(ge=0)]] = 500

    # Step 5: House Rules
    house_rules: Optional[List[str]] = Field(default_factory=list)
    main_residence: Optional[bool] = None

    # Step 6: Transport & Car Swap
    open_to_car_swap: bool = False
    require_car_swap_match: bool = False
    car_details: Optional[Dict[str, Any]] = None

    # Step 7:  Available Amenities
    amenities: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
    accessibility_features: Optional[List[str]] = Field(default_factory=list)
    parking_type: Optional[Literal["none", "street", "driveway", "garage", "covered"]] = None

    # Step 8: Availability
    is_flexible: Optional[bool] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None

    # Step 9: Title and Description (Required: title; Optional: description)
    title: Annotated[str, Field(max_length=200, min_length=5)]
    description: Optional[Annotated[str, Field(max_length=5000, min_length=10)]] = None

    # Status (will default in DB)
    status: Optional[Literal["draft", "published", "archived"]] = "draft"


class ImageMetadataItem(BaseModel):
    caption: Optional[Annotated[str, Field(max_length=200)]] = None
    tag: Optional[Annotated[str, Field(max_length=100)]] = None
    is_hero: Optional[bool] = False
    sort_order: Optional[Annotated[int, Field(ge=0)]] = None

    # Just for editing existing listing:
    public_url: Optional[Annotated[str, Field(max_length=2048)]] = None
    cdn_url: Optional[Annotated[str, Field(max_length=2048)]] = None


class ImageMetadataCollection(BaseModel):
    images_metadata: Optional[List[ImageMetadataItem]] = Field(default_factory=list)
    deleted_public_urls: Optional[List[Annotated[str, Field(max_length=2048)]]] = Field(
        default_factory=list
    )


class FullHomeListing(HomeListingCreate):
    images: Optional[List[ImageMetadataItem]] = Field(default_factory=list)


class UserCreate(BaseModel):
    owner_firebase_uid: str
    email: Annotated[EmailStr, Field(max_length=255)]
    name: Annotated[str, Field(max_length=100, min_length=2)]
    profile_image: Optional[Annotated[str, Field(max_length=500)]] = None
    is_email_verified: bool


class UserUpdate(BaseModel):
    name: Optional[Annotated[str, Field(max_length=100, min_length=2)]] = None
    phone_country_code: Optional[Annotated[str, Field(max_length=5, min_length=2)]] = None
    phone_number: Optional[Annotated[str, Field(pattern=r"^\d{4,15}$")]] = None
    linkedin_url: Optional[Annotated[str, Field(max_length=200, min_length=5)]] = None
    instagram_id: Optional[Annotated[str, Field(max_length=100, min_length=2)]] = None
    facebook_id: Optional[Annotated[str, Field(max_length=100, min_length=2)]] = None
    profile_image: Optional[Annotated[str, Field(max_length=500)]] = None


class FirebaseUserIfNotExists(BaseModel):
    owner_firebase_uid: str
    email: Optional[Annotated[EmailStr, Field(max_length=255)]] = None
    name: Optional[Annotated[str, Field(max_length=100, min_length=2)]] = None
    profile_image: Optional[str] = None


#  You need validators for:

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
