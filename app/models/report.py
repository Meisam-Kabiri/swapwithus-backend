"""
Report models for content moderation
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.utils import snake_to_camel


class ReportCreate(BaseModel):
    """Schema for creating a new report"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    reported_uid: str | None = Field(
        None,
        description="Firebase UID of the reported user (if reporting a user)"
    )
    reported_listing_id: str | None = Field(  # Changed to str for UUID
        None,
        description="ID of the reported listing (if reporting a listing)"
    )
    reported_swap_id: str | None = Field(  # Changed to str for UUID  
        None,
        description="ID of the reported swap (if reporting a swap)"
    )
    reported_message_id: str | None = Field(
        None,
        description="ID of the reported message (if reporting a message)"
    )
    report_type: Literal["spam", "scam", "inappropriate", "harassment", "fraud", "other"] = Field(
        ...,
        description="Type of report"
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Detailed description of the issue"
    )


class ReportResponse(BaseModel):
    """Schema for report response"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore",
        from_attributes=True
    )

    id: int
    reporter_uid: str
    reported_uid: str | None
    reported_listing_id: str | None  # Changed to str for UUID
    reported_swap_id: str | None     # Changed to str for UUID
    reported_message_id: str | None
    report_type: str
    description: str
    status: str
    resolution_action: str | None
    resolution_notes: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime


class ReportWithDetails(ReportResponse):
    """Extended report with reporter details"""

    reporter_email: str | None
    reporter_name: str | None
    reported_user_email: str | None
    reported_user_name: str | None


class ReportResolve(BaseModel):
    """Schema for resolving a report"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    action: Literal["dismiss", "warn", "ban_user", "delete_content", "other"] = Field(
        ...,
        description="Action taken to resolve the report"
    )
    notes: str | None = Field(
        None,
        max_length=1000,
        description="Optional notes about the resolution"
    )
