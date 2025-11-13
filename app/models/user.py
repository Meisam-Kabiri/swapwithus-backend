from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.home_listing import snake_to_camel


class UserCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
      )
    owner_firebase_uid: str
    email: Annotated[EmailStr, Field(max_length=255)]
    name: Annotated[str, Field(max_length=100, min_length=2)]
    profile_image: Annotated[str, Field(max_length=500)] | None = None
    is_email_verified: bool


class UserUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )
    name: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    phone_country_code: Annotated[str, Field(max_length=5, min_length=2)] | None = None
    phone_number: Annotated[str, Field(pattern=r"^\d{4,15}$")] | None = None
    linkedin_url: Annotated[str, Field(max_length=200, min_length=5)] | None = None
    instagram_id: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    facebook_id: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    profile_image: Annotated[str, Field(max_length=500)] | None = None


class FirebaseUserUpsert(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )
    owner_firebase_uid: str
    email: Annotated[EmailStr, Field(max_length=255)] | None = None
    name: Annotated[str, Field(max_length=100, min_length=2)] | None = None
    profile_image: str | None = None
