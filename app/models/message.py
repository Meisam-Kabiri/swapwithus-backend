from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.utils import snake_to_camel


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    recipient_uid: Annotated[str, Field(min_length=1, max_length=128)]
    requester_listing_id: Optional[str] = None
    recipient_listing_id: Optional[str] = None
    initial_message: Annotated[str, Field(min_length=1, max_length=2000)]
    media_url: Optional[str] = None
    media_type: Optional[Literal["image", "video"]] = None

    @field_validator("initial_message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        import re

        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        # Block script tags and suspicious patterns
        if re.search(r"<script|javascript:|on\w+\s*=", v, re.IGNORECASE):
            raise ValueError("Message contains prohibited content")
        return v

    @field_validator("media_url")
    @classmethod
    def validate_firebase_url(cls, v: Optional[str]) -> Optional[str]:
        """Ensure media_url is from Firebase Storage"""
        if v is None:
            return None
        if not v.startswith("https://firebasestorage.googleapis.com/"):
            raise ValueError("media_url must be a Firebase Storage URL")
        return v


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    text: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[Literal["image", "video"]] = None

    @field_validator("text")
    @classmethod
    def sanitize_message(cls, v: Optional[str]) -> Optional[str]:
        import re

        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if re.search(r"<script|javascript:|on\w+\s*=", v, re.IGNORECASE):
            raise ValueError("Message contains prohibited content")
        return v

    @field_validator("media_url")
    @classmethod
    def validate_firebase_url(cls, v: Optional[str]) -> Optional[str]:
        """Ensure media_url is from Firebase Storage"""
        if v is None:
            return None
        if not v.startswith("https://firebasestorage.googleapis.com/"):
            raise ValueError("media_url must be a Firebase Storage URL")
        return v

    def model_post_init(self, __context) -> None:
        """Validate that at least text or media is provided"""
        has_text = self.text is not None and self.text.strip() != ""
        has_media = self.media_url is not None

        if not has_text and not has_media:
            raise ValueError("Message must contain either text or media")
        if has_media and not self.media_type:
            raise ValueError("media_type is required when media_url is provided")


class ConversationStatusUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, populate_by_name=True)

    status: Annotated[str, Field(pattern="^(accepted|declined)$")]
