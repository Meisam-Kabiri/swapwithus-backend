from typing import Annotated, List

from pydantic import BaseModel, ConfigDict, Field

from app.models.utils import snake_to_camel


class ImageMetadataItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )
    
    caption: Annotated[str, Field(max_length=200)] | None = None
    tag: Annotated[str, Field(max_length=100)] | None = None
    is_hero: bool | None = False
    sort_order: Annotated[int, Field(ge=0)] | None = None

    # Just for editing existing listing:
    public_url: Annotated[str, Field(max_length=2048)] | None = None
    cdn_url: Annotated[str, Field(max_length=2048)] | None = None


class ImageMetadataCollection(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )
    images_metadata: List[ImageMetadataItem] | None = Field(default_factory=list)
    deleted_public_urls: List[Annotated[str, Field(max_length=2048)]] | None = Field(
        default_factory=list
    )

