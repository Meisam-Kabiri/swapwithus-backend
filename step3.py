"""
STEP 3: API Data Models & Type Safety

SwapWithUs Pydantic Models - Professional API Interface

=== WHAT THIS STEP DOES ===
This step defines all data models for your swap platform's API using Pydantic for automatic
validation, serialization, and type safety that integrates perfectly with your database operations.

=== ARCHITECTURE EXPLANATION ===
Following your SPEED + SECURITY focused architecture:

1. TYPE SAFETY & VALIDATION:
   - Pydantic models provide automatic input validation
   - Type hints ensure code quality and IDE support
   - Automatic data conversion and error messages
   - Prevents invalid data from reaching your database

2. API REQUEST/RESPONSE MODELS:
   - CreateListingRequest - Validates incoming listing data
   - UpdateListingRequest - Validates listing modifications
   - SearchListingsRequest - Validates search parameters
   - ListingResponse - Standardized API responses

3. CATEGORY-SPECIFIC VALIDATION:
   - Separate models for each category (homes, clothes, books, etc.)
   - Dynamic validation based on listing category
   - Ensures category_data matches expected structure
   - Flexible yet type-safe JSON handling

4. DATABASE INTEGRATION:
   - from_db_row() methods convert asyncpg results to Pydantic models
   - Automatic JSON parsing from database JSONB fields
   - Seamless integration with Step 2's repository operations
   - Type-safe data flow from database to API

5. PROFESSIONAL API FEATURES:
   - Email validation for contact information
   - Enum types for consistent categories and statuses
   - Pagination models for search results
   - Comprehensive field validation with regex patterns

=== WHY THIS APPROACH FOR SWAPWITHUS.COM ===
- Prevents 90% of API bugs through validation
- Professional API documentation (auto-generated from models)
- Frontend gets clear data structure contracts
- Team collaboration with type hints and validation
- Production-ready error handling and user feedback
- Scales with complex swap platform requirements

=== MODELS DEFINED ===
1. Category-specific models (HomesCategoryData, ClothesCategoryData, etc.)
2. Request models (CreateListingRequest, UpdateListingRequest, SearchListingsRequest)
3. Response models (ListingResponse, SearchListingsResponse, UserProfile)
4. Enum types (ListingCategory, ItemCondition, ListingStatus)
5. Integration utilities (from_db_row converters)

=== FASTAPI INTEGRATION ===
These models work directly with FastAPI for automatic:
- Request validation and error responses
- Response serialization and documentation
- OpenAPI/Swagger documentation generation
- Type-safe endpoint development
"""

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from enum import Enum
import json

# Enums for better type safety
class ListingCategory(str, Enum):
    HOMES = "homes"
    CLOTHES = "clothes"
    BOOKS = "books"
    ELECTRONICS = "electronics"
    SPORTS = "sports"
    VEHICLES = "vehicles"
    SERVICES = "services"

class ItemCondition(str, Enum):
    NEW = "new"
    LIKE_NEW = "like-new"
    GOOD = "good"
    FAIR = "fair"

class ListingStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    SWAPPED = "swapped"
    DELETED = "deleted"

# Category-specific data models
class HomesCategoryData(BaseModel):
    property_type: Optional[str] = Field(None, regex="^(apartment|house|cottage|villa|cabin)$")
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    bathrooms: Optional[float] = Field(None, ge=0, le=20)
    max_guests: Optional[int] = Field(None, ge=1, le=50)
    square_feet: Optional[int] = Field(None, ge=0)
    amenities: Optional[List[str]] = []
    house_rules: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None

class ClothesCategoryData(BaseModel):
    brand: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = Field(None, regex="^(unisex|mens|womens|kids)$")
    season: Optional[str] = Field(None, regex="^(spring|summer|fall|winter|all)$")
    material: Optional[str] = None

class BooksCategoryData(BaseModel):
    author: Optional[str] = None
    genre: Optional[str] = None
    isbn: Optional[str] = None
    publication_year: Optional[str] = None
    language: Optional[str] = Field(default="english")
    format: Optional[str] = Field(None, regex="^(paperback|hardcover|audiobook|ebook)$")
    series: Optional[str] = None
    volume_count: Optional[int] = Field(None, ge=1)

class ElectronicsCategoryData(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    specifications: Optional[str] = None
    warranty_status: Optional[str] = Field(None, regex="^(active|expired|unknown)$")
    accessories_included: Optional[str] = None

class SportsCategoryData(BaseModel):
    sport: Optional[str] = None
    brand: Optional[str] = None
    size_weight: Optional[str] = None
    skill_level: Optional[str] = Field(None, regex="^(beginner|intermediate|advanced)$")
    safety_certification: Optional[str] = None

class VehiclesCategoryData(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    mileage: Optional[str] = None
    fuel_type: Optional[str] = Field(None, regex="^(gasoline|diesel|electric|hybrid)$")
    insurance_required: Optional[bool] = True

class ServicesCategoryData(BaseModel):
    service_type: Optional[str] = None
    duration: Optional[str] = None
    skill_level: Optional[str] = Field(None, regex="^(beginner|intermediate|expert)$")
    availability_hours: Optional[str] = None

# Union type for all category data
CategoryDataUnion = Union[
    HomesCategoryData,
    ClothesCategoryData,
    BooksCategoryData,
    ElectronicsCategoryData,
    SportsCategoryData,
    VehiclesCategoryData,
    ServicesCategoryData
]

# Request models (for API input validation)
class CreateListingRequest(BaseModel):
    """Model for creating a new listing - matches your frontend form"""
    # Basic info
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=20)
    category: ListingCategory
    condition: ItemCondition = ItemCondition.GOOD

    # Location
    city: str = Field(..., min_length=2, max_length=100)
    country: str = Field(..., min_length=2, max_length=100)
    address: Optional[str] = None

    # Availability
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    value_estimate: Optional[str] = None
    preferred_swap_categories: Optional[List[ListingCategory]] = []

    # Contact
    contact_name: str = Field(..., min_length=2, max_length=255)
    contact_email: EmailStr
    contact_phone: Optional[str] = None

    # Category-specific data (this maps to your frontend's categorySpecific)
    category_data: Optional[Dict[str, Any]] = {}

    # Media
    photos: Optional[List[str]] = []

    @validator('category_data')
    def validate_category_data(cls, v, values):
        """Validate category_data based on category type"""
        if not v:
            return {}

        category = values.get('category')
        if not category:
            return v

        # Validate based on category
        try:
            if category == ListingCategory.HOMES:
                HomesCategoryData(**v)
            elif category == ListingCategory.CLOTHES:
                ClothesCategoryData(**v)
            elif category == ListingCategory.BOOKS:
                BooksCategoryData(**v)
            elif category == ListingCategory.ELECTRONICS:
                ElectronicsCategoryData(**v)
            elif category == ListingCategory.SPORTS:
                SportsCategoryData(**v)
            elif category == ListingCategory.VEHICLES:
                VehiclesCategoryData(**v)
            elif category == ListingCategory.SERVICES:
                ServicesCategoryData(**v)
        except Exception as e:
            raise ValueError(f"Invalid category_data for {category}: {e}")

        return v

class UpdateListingRequest(BaseModel):
    """Model for updating listings - all fields optional"""
    title: Optional[str] = Field(None, min_length=5, max_length=255)
    description: Optional[str] = Field(None, min_length=20)
    condition: Optional[ItemCondition] = None
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    country: Optional[str] = Field(None, min_length=2, max_length=100)
    address: Optional[str] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    value_estimate: Optional[str] = None
    preferred_swap_categories: Optional[List[ListingCategory]] = None
    contact_name: Optional[str] = Field(None, min_length=2, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    category_data: Optional[Dict[str, Any]] = None
    photos: Optional[List[str]] = None
    status: Optional[ListingStatus] = None

# Response models (for API output)
class UserProfile(BaseModel):
    """User profile info included in listing responses"""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    trust_score: Optional[int] = 0
    verification_level: Optional[str] = "unverified"

class ListingResponse(BaseModel):
    """Complete listing response model"""
    # Basic identification
    id: int
    listing_uuid: str

    # User info
    owner_id: int
    owner: Optional[UserProfile] = None

    # Basic listing info
    title: str
    description: str
    category: ListingCategory
    condition: ItemCondition

    # Location
    city: str
    country: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Availability
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    value_estimate: Optional[str] = None
    preferred_swap_categories: Optional[List[ListingCategory]] = []

    # Contact
    contact_name: str
    contact_email: EmailStr
    contact_phone: Optional[str] = None

    # Media
    photos: Optional[List[str]] = []
    main_photo: Optional[str] = None

    # Category-specific data
    category_data: Optional[Dict[str, Any]] = {}

    # Status & metadata
    status: ListingStatus
    moderation_status: Optional[str] = None
    is_featured: bool = False
    view_count: int = 0
    inquiry_count: int = 0

    # SEO
    slug: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'ListingResponse':
        """Convert database row to Pydantic model"""
        # Parse JSON fields if they're strings
        category_data = row.get('category_data', {})
        if isinstance(category_data, str):
            category_data = json.loads(category_data) if category_data else {}

        # Build owner profile if user data exists
        owner = None
        if row.get('first_name') or row.get('last_name'):
            owner = UserProfile(
                id=row['owner_id'],
                first_name=row.get('first_name'),
                last_name=row.get('last_name'),
                avatar_url=row.get('avatar_url'),
                trust_score=row.get('trust_score', 0),
                verification_level=row.get('verification_level', 'unverified')
            )

        return cls(
            id=row['id'],
            listing_uuid=str(row['listing_uuid']),
            owner_id=row['owner_id'],
            owner=owner,
            title=row['title'],
            description=row['description'],
            category=ListingCategory(row['category']),
            condition=ItemCondition(row['condition']),
            city=row['city'],
            country=row['country'],
            address=row.get('address'),
            latitude=float(row['latitude']) if row.get('latitude') else None,
            longitude=float(row['longitude']) if row.get('longitude') else None,
            available_from=row.get('available_from'),
            available_until=row.get('available_until'),
            value_estimate=row.get('value_estimate'),
            preferred_swap_categories=[ListingCategory(cat) for cat in (row.get('preferred_swap_categories') or [])],
            contact_name=row['contact_name'],
            contact_email=row['contact_email'],
            contact_phone=row.get('contact_phone'),
            photos=row.get('photos', []),
            main_photo=row.get('main_photo'),
            category_data=category_data,
            status=ListingStatus(row['status']),
            moderation_status=row.get('moderation_status'),
            is_featured=row.get('is_featured', False),
            view_count=row.get('view_count', 0),
            inquiry_count=row.get('inquiry_count', 0),
            slug=row.get('slug'),
            created_at=row['created_at'],
            updated_at=row.get('updated_at')
        )

# Search request/response models
class SearchListingsRequest(BaseModel):
    """Model for search API requests"""
    category: Optional[ListingCategory] = None
    city: Optional[str] = None
    country: Optional[str] = None
    condition: Optional[List[ItemCondition]] = None

    # JSON-based filters
    min_bedrooms: Optional[int] = Field(None, ge=0)
    max_bedrooms: Optional[int] = Field(None, ge=0)
    brand: Optional[str] = None
    size: Optional[str] = None
    author: Optional[str] = None
    amenities: Optional[List[str]] = None

    # Pagination
    page: Optional[int] = Field(default=1, ge=1)
    per_page: Optional[int] = Field(default=20, ge=1, le=100)

    # Sorting
    sort_by: Optional[str] = Field(default="created_at", regex="^(created_at|view_count|title)$")
    sort_order: Optional[str] = Field(default="desc", regex="^(asc|desc)$")

class SearchListingsResponse(BaseModel):
    """Model for search API responses"""
    listings: List[ListingResponse]
    total_count: int
    page: int
    per_page: int
    has_next: bool
    total_pages: int

    @classmethod
    def from_db_result(cls, db_result: Dict[str, Any]) -> 'SearchListingsResponse':
        """Convert database search result to Pydantic response"""
        listings = [
            ListingResponse.from_db_row(row)
            for row in db_result['listings']
        ]

        return cls(
            listings=listings,
            total_count=db_result['total_count'],
            page=db_result['page'],
            per_page=db_result['per_page'],
            has_next=db_result['has_next'],
            total_pages=db_result.get('total_pages', 0)
        )

# FastAPI integration example
"""
# In your FastAPI routes:

from fastapi import FastAPI, HTTPException
from .models import CreateListingRequest, ListingResponse, SearchListingsRequest

app = FastAPI()

@app.post("/listings", response_model=ListingResponse)
async def create_listing(request: CreateListingRequest):
    # Convert Pydantic model to dict for database
    listing_data = request.dict()
    
    # Your asyncpg repository call
    result = await listings_repo.create_listing(listing_data)
    
    # Convert database result back to Pydantic response
    return ListingResponse.from_db_row(result)

@app.get("/listings/search", response_model=SearchListingsResponse) 
async def search_listings(request: SearchListingsRequest):
    # Convert to filters dict
    filters = request.dict(exclude_unset=True, exclude={'page', 'per_page'})
    
    # Database call
    db_result = await listings_repo.search_listings(
        filters, request.page, request.per_page
    )
    
    # Convert to response model
    return SearchListingsResponse.from_db_result(db_result)
"""
