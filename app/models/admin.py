"""
Admin-specific models
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.utils import snake_to_camel


class DashboardStats(BaseModel):
    """Statistics for admin dashboard overview"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    total_users: int
    active_users: int  # Non-banned users
    banned_users: int
    total_listings: int  # Aggregate count from homes, books, caravans, clothes
    active_listings: int  # Count of published listings across all types
    total_swaps: int
    swaps_pending: int
    swaps_active: int
    swaps_completed: int
    swaps_cancelled: int
    pending_reports: int
    new_users_7d: int  # New users in last 7 days
    new_users_30d: int  # New users in last 30 days
    new_listings_7d: int  # New listings across all types in last 7 days
    new_swaps_7d: int


class UserManagement(BaseModel):
    """User information for admin management"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore",
        from_attributes=True
    )

    owner_firebase_uid: str  # This is the actual field name from database
    email: str
    display_name: str | None  # Will be mapped from 'name' in the query
    trust_score: int | None
    total_swaps: int
    completed_swaps: int
    average_rating: float | None
    is_banned: bool
    is_admin: bool
    ban_reason: str | None
    banned_at: datetime | None
    created_at: datetime
    last_active: datetime | None


class BanUserRequest(BaseModel):
    """Request to ban a user"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Reason for banning the user"
    )
    permanent: bool = Field(
        True,
        description="Whether the ban is permanent"
    )
    ban_duration_days: int | None = Field(
        None,
        ge=1,
        le=365,
        description="Duration of ban in days (if not permanent)"
    )


class SwapManagement(BaseModel):
    """Swap information for admin management"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore",
        from_attributes=True
    )

    id: str  # Changed from int to str since swap_id is UUID
    requester_uid: str
    requester_email: str | None
    requester_name: str | None
    recipient_uid: str
    recipient_email: str | None
    recipient_name: str | None
    status: str
    requested_item_title: str | None
    offered_item_title: str | None
    initiated_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


class PaginatedResponse(BaseModel):
    """Generic paginated response"""

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra="ignore"
    )

    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
