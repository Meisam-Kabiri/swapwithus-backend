import io
from uuid import uuid4

from faker import Faker
from fastapi import UploadFile
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use
from pydantic import BaseModel
from starlette.datastructures import Headers

from app.models.book_listing import BookListingCreate, BookListingResponse
from app.models.caravan_listing import CaravanListingCreate, CaravanListingResponse
from app.models.clothing_listing import ClothingListingCreate, ClothingListingResponse
from app.models.home_listing import HomeListingCreate, HomeListingResponse
from app.models.image import ImageMetadataCollection, ImageMetadataItem
from app.models.message import CreateConversationRequest, SendMessageRequest, ConversationStatusUpdate
from app.models.swap import SwapCreate, SwapUpdate
from app.models.user import UserCreate

fake = Faker()


class UserCreateFactory(ModelFactory[UserCreate]):
    """Factory for generating fake UserCreate data"""

    __model__ = UserCreate
    __check_model__ = False  # Suppress deprecation warning

    # Tell polyfactory how to generate EmailStr
    email = Use(lambda: fake.email())

    # Generate realistic Firebase UID (28 chars, matching Firebase UID format)
    owner_firebase_uid = Use(lambda: uuid4().hex[:20])


class HomeListingCreateFactory(ModelFactory[HomeListingCreate]):
    """Factory for generating fake HomeListingCreate data"""

    __model__ = HomeListingCreate
    __check_model__ = False  # Suppress deprecation warning

    # Only override fields that polyfactory can't handle properly
    email = Use(lambda: fake.email())
    owner_firebase_uid = Use(lambda: uuid4().hex[:20])


class HomeListingUpdateCreateFactoryDict:
    """Only Generate some fields for Home fields for update testing purpose"""

    def __init__(self):
        # Slice to match database VARCHAR constraints (not just Pydantic)
        self.country = fake.country()[:20]
        self.city = fake.city()[:50]
        self.postal_code = fake.postcode()[:20]
        self.surroundings_type = fake.word()[:20]
        self.title = fake.sentence(nb_words=6)[:100]
        self.name = fake.name()[:100]

    def build_updated_data(self):
        return {
            "country": self.country,
            "city": self.city,
            "postal_code": self.postal_code,
            "surroundings_type": self.surroundings_type,
            "title": self.title,
            "name": self.name,
        }

    def build_image_metadata(self, files_num):
        fake_meta_data = [
            ImageMetadataItem(
                caption=fake.sentence(nb_words=3)[:200],  # Slice for safety in manual builder
                tag=fake.word()[:100],  # Slice for safety in manual builder
                is_hero=(i == 0),
                sort_order=i,
                public_url="",
                cdn_url="",
            )
            for i in range(files_num)
        ]
        return [item.model_dump() for item in fake_meta_data]

    def build_data_form(self):
        return {
            "country": self.country,
            "city": self.city,
            "postal_code": self.postal_code,
            "surroundings_type": self.surroundings_type,
            "title": self.title,
            "name": self.name,
        }


class HomeListingResponseFactory(ModelFactory[HomeListingResponse]):
    """Factory for generating fake HomeListingResponse data"""

    __model__ = HomeListingResponse
    __check_model__ = False  # Suppress deprecation warning


class BookListingCreateFactory(ModelFactory[BookListingCreate]):
    """Factory for generating fake BookListingCreate data"""

    __model__ = BookListingCreate
    __check_model__ = False  # Suppress deprecation warning

    # Only override fields that polyfactory can't handle properly
    owner_firebase_uid = Use(lambda: uuid4().hex[:20])


class BookListingResponseFactory(ModelFactory[BookListingResponse]):
    """Factory for generating fake BookListingResponse data"""

    __model__ = BookListingResponse
    __check_model__ = False  # Suppress deprecation warning


class CaravanListingCreateFactory(ModelFactory[CaravanListingCreate]):
    """Factory for generating fake CaravanListingCreate data"""

    __model__ = CaravanListingCreate
    __check_model__ = False

    # Only override fields that polyfactory can't handle properly
    owner_firebase_uid = Use(lambda: uuid4().hex[:20])
    email = Use(lambda: fake.email())


class CaravanListingResponseFactory(ModelFactory[CaravanListingResponse]):
    """Factory for generating fake CaravanListingResponse data"""

    __model__ = CaravanListingResponse
    __check_model__ = False  # Suppress deprecation warning


class ClothingListingCreateFactory(ModelFactory[ClothingListingCreate]):
    """Factory for generating fake ClothingListingCreate data"""

    __model__ = ClothingListingCreate
    __check_model__ = False

    # Only override fields that polyfactory can't handle properly
    owner_firebase_uid = Use(lambda: uuid4().hex[:20])
    email = Use(lambda: fake.email())


class ClothingListingResponseFactory(ModelFactory[ClothingListingResponse]):
    """Factory for generating fake ClothingListingResponse data"""

    __model__ = ClothingListingResponse
    __check_model__ = False  # Suppress deprecation warning


class ImageMetadataItemFactory(ModelFactory[ImageMetadataItem]):
    """Factory for generating fake ImageMetadataItem data"""

    __model__ = ImageMetadataItem


class ImageMetadataCollectionFactory(ModelFactory[ImageMetadataCollection]):
    """Factory for generating fake ImageMetadataCollection data"""

    __model__ = ImageMetadataCollection
    __check_model__ = False  # Suppress deprecation warning


class FileClass(BaseModel):
    """Model for generating fake file data"""

    filename: str
    content: bytes
    content_type: str


class FakeFileFactory(ModelFactory[FileClass]):
    """Factory for generating fake file data for UploadFile mocking"""

    __model__ = FileClass
    __check_model__ = False  # Suppress deprecation warning

    # Override to generate realistic image file names and content
    filename = Use(lambda: f"test_image_{fake.random_int(min=1, max=999)}.jpg")
    content = Use(lambda: f"fake image content {fake.random_int(min=1, max=999)}".encode())
    content_type = Use(lambda: "image/jpeg")


def fake_uploadfile_list(count: int = 3) -> list[UploadFile]:
    """
    Create a list of mock UploadFile objects for testing

    Args:
        count: Number of UploadFile objects to create

    Returns:
        List of UploadFile objects with fake data

    Example:
        >>> files = create_uploadfile_list(5)
        >>> len(files)
        5
        >>> files[0].filename
        'test_image_123.jpg'
    """
    files = []
    for _ in range(count):
        file = FakeFileFactory.build()
        upload_file = UploadFile(
            filename=file.filename,
            file=io.BytesIO(file.content),
            headers=Headers({"content-type": file.content_type}),
        )
        files.append(upload_file)
    return files


class SwapCreateFactory(ModelFactory[SwapCreate]):
    """Factory for generating fake SwapCreate data"""

    __model__ = SwapCreate
    __check_model__ = False  # Suppress deprecation warning

    # Override fields that need specific formats
    user_b_uid = Use(lambda: uuid4().hex[:20])
    listing_a_id = Use(lambda: str(uuid4()))
    listing_b_id = Use(lambda: str(uuid4()))
    listing_a_category = Use(lambda: fake.random_element(elements=["homes", "books", "clothes", "caravans"]))
    listing_b_category = Use(lambda: fake.random_element(elements=["homes", "books", "clothes", "caravans"]))
    conversation_id = Use(lambda: uuid4().hex[:20] if fake.boolean() else None)


class SwapUpdateFactory(ModelFactory[SwapUpdate]):
    """Factory for generating fake SwapUpdate data"""

    __model__ = SwapUpdate
    __check_model__ = False  # Suppress deprecation warning

    status = Use(lambda: fake.random_element(elements=["pending", "accepted", "completed", "cancelled"]))
    cancellation_reason = Use(lambda: fake.sentence() if fake.boolean() else None)


class CreateConversationRequestFactory(ModelFactory[CreateConversationRequest]):
    """Factory for generating fake CreateConversationRequest data"""

    __model__ = CreateConversationRequest
    __check_model__ = False  # Suppress deprecation warning

    recipient_uid = Use(lambda: uuid4().hex[:20])
    requester_listing_id = Use(lambda: str(uuid4()) if fake.boolean() else None)
    recipient_listing_id = Use(lambda: str(uuid4()) if fake.boolean() else None)
    requester_listing_category = Use(lambda: fake.random_element(elements=["homes", "books", "clothes", "caravans"]) if fake.boolean() else None)
    recipient_listing_category = Use(lambda: fake.random_element(elements=["homes", "books", "clothes", "caravans"]) if fake.boolean() else None)
    initial_message = Use(lambda: fake.sentence(nb_words=10))
    media_url = None  # Set to None by default since it needs to be a Firebase URL
    media_type = None


class SendMessageRequestFactory(ModelFactory[SendMessageRequest]):
    """Factory for generating fake SendMessageRequest data"""

    __model__ = SendMessageRequest
    __check_model__ = False  # Suppress deprecation warning

    text = Use(lambda: fake.sentence(nb_words=10))
    media_url = None  # Set to None by default since it needs to be a Firebase URL
    media_type = None


class ConversationStatusUpdateFactory(ModelFactory[ConversationStatusUpdate]):
    """Factory for generating fake ConversationStatusUpdate data"""

    __model__ = ConversationStatusUpdate
    __check_model__ = False  # Suppress deprecation warning

    status = Use(lambda: fake.random_element(elements=["accepted", "declined"]))


# ============================================
# DATABASE HELPER FUNCTIONS
# Reusable functions to insert test data into the database
# ============================================

from datetime import datetime


async def add_user(
    pool,
    uid: str | None = None,
    email: str | None = None,
    name: str | None = None,
    is_email_verified: bool = True,
    is_admin: bool = False,
    is_banned: bool = False
) -> str:
    """
    Insert a test user into the database

    Returns:
        str: The user's Firebase UID

    Example:
        user_id = await add_user(pool, email="test@example.com")
        admin_id = await add_user(pool, is_admin=True)
    """
    uid = uid or f"test_user_{uuid4()}"
    email = email or f"{uid}@test.com"
    name = name or fake.name()

    await pool.execute(
        """
        INSERT INTO users (
            owner_firebase_uid, email, name, is_email_verified, is_admin, is_banned
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (owner_firebase_uid) DO NOTHING
        """,
        uid, email, name, is_email_verified, is_admin, is_banned
    )
    return uid


async def add_listing(
    pool,
    owner_uid: str,
    category: str,  # "homes", "books", "caravans", "clothes"
    listing_id: str | None = None,
    num_images: int = 3,
    **kwargs
) -> str:
    """
    Insert a test listing into the database using Pydantic factories

    Args:
        pool: Database pool
        owner_uid: Owner's Firebase UID
        category: "homes", "books", "caravans", or "clothes"
        listing_id: Optional custom ID
        num_images: Number of test images to create (default 3)
        **kwargs: Override factory fields

    Returns:
        str: The listing ID

    Examples:
        listing_id = await add_listing(pool, user_id, "homes")
        listing_id = await add_listing(pool, user_id, "homes", num_images=5)
        book_id = await add_listing(pool, user_id, "books", title="1984", author="Orwell")
    """
    import json
    listing_id = listing_id or str(uuid4())

    if category == "homes":
        data = HomeListingCreateFactory.build(**kwargs).model_dump(exclude={"listing_id", "owner_firebase_uid"})
        # Convert ONLY dict fields to JSON strings for JSONB columns (keep arrays and dates as-is)
        for key, value in data.items():
            if isinstance(value, dict):
                data[key] = json.dumps(value)
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data) + 2)])
        await pool.execute(
            f"INSERT INTO homes (listing_id, owner_firebase_uid, {cols}) VALUES ({placeholders})",
            listing_id, owner_uid, *data.values()
        )

    elif category == "books":
        data = BookListingCreateFactory.build(**kwargs).model_dump(exclude={"listing_id", "owner_firebase_uid"})
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data) + 2)])
        await pool.execute(
            f"INSERT INTO books (listing_id, owner_firebase_uid, {cols}) VALUES ({placeholders})",
            listing_id, owner_uid, *data.values()
        )

    elif category == "caravans":
        data = CaravanListingCreateFactory.build(**kwargs).model_dump(exclude={"listing_id", "owner_firebase_uid"})
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data) + 2)])
        await pool.execute(
            f"INSERT INTO caravans (listing_id, owner_firebase_uid, {cols}) VALUES ({placeholders})",
            listing_id, owner_uid, *data.values()
        )

    elif category == "clothes":
        data = ClothingListingCreateFactory.build(**kwargs).model_dump(exclude={"listing_id", "owner_firebase_uid"})
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data) + 2)])
        await pool.execute(
            f"INSERT INTO clothes (listing_id, owner_firebase_uid, {cols}) VALUES ({placeholders})",
            listing_id, owner_uid, *data.values()
        )

    else:
        raise ValueError(f"Unknown category: {category}. Must be: homes, books, caravans, or clothes")

    # Create images and upload to GCP test_images folder
    if num_images > 0:
        from app.services.gcp_image_service import upload_photo_to_storage

        for i in range(num_images):
            # Create fake image file
            fake_image = FakeFileFactory.build()
            upload_file = UploadFile(
                filename=fake_image.filename,
                file=io.BytesIO(fake_image.content),
                headers=Headers({"content-type": fake_image.content_type}),
            )

            # Upload to GCP test_images folder
            public_url = await upload_photo_to_storage(upload_file, listing_id, "test_images")

            # Insert into images table
            await pool.execute(
                """
                INSERT INTO images (
                    owner_firebase_uid, listing_id, category,
                    public_url, cdn_url, tag, caption,
                    sort_order, is_hero
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                owner_uid, listing_id, category,
                public_url, public_url,  # Use same URL for cdn_url
                fake.word()[:100], fake.sentence(nb_words=5),
                i, i == 0  # First image is hero
            )

    return listing_id


async def add_swap(
    pool,
    user_a_uid: str,
    user_b_uid: str,
    listing_a_id: str,
    listing_b_id: str,
    listing_a_category: str = "homes",
    listing_b_category: str = "homes",
    status: str = "pending",
    swap_id: str | None = None
) -> str:
    """
    Insert a test swap into the database

    Returns:
        str: The swap ID

    Example:
        swap_id = await add_swap(pool, user_a, user_b, listing_a, listing_b)
    """
    swap_id = swap_id or str(uuid4())

    await pool.execute(
        """
        INSERT INTO swaps (
            swap_id, user_a_uid, user_b_uid,
            listing_a_id, listing_b_id,
            listing_a_category, listing_b_category,
            status, initiated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        swap_id, user_a_uid, user_b_uid,
        listing_a_id, listing_b_id,
        listing_a_category, listing_b_category,
        status, datetime.utcnow()
    )
    return swap_id


async def add_review(
    pool,
    swap_id: str,
    reviewer_uid: str,
    reviewed_uid: str,
    rating: int = 5,
    comment: str | None = None
) -> int:
    """
    Insert a test review into the database

    Returns:
        int: The review ID

    Example:
        review_id = await add_review(pool, swap_id, user_a, user_b, rating=5)
    """
    comment = comment or fake.text(max_nb_chars=200)

    result = await pool.fetchval(
        """
        INSERT INTO reviews (
            swap_id, reviewer_uid, reviewed_uid, rating, comment, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING review_id
        """,
        swap_id, reviewer_uid, reviewed_uid, rating, comment, datetime.utcnow()
    )
    return result


async def add_favorite(
    pool,
    user_uid: str,
    listing_id: str
) -> None:
    """
    Insert a test favorite into the database

    Example:
        await add_favorite(pool, user_id, listing_id)
    """
    await pool.execute(
        """
        INSERT INTO favorites (user_uid, listing_id, created_at)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        user_uid, listing_id, datetime.utcnow()
    )


async def add_report(
    pool,
    reporter_uid: str,
    report_type: str = "spam",
    description: str | None = None,
    reported_uid: str | None = None,
    reported_listing_id: str | None = None,
    reported_swap_id: str | None = None
) -> int:
    """
    Insert a test report into the database

    Returns:
        int: The report ID

    Example:
        report_id = await add_report(pool, user_id, reported_uid=bad_user_id)
    """
    description = description or fake.text(max_nb_chars=200)

    result = await pool.fetchval(
        """
        INSERT INTO reports (
            reporter_uid, reported_uid, reported_listing_id, reported_swap_id,
            report_type, description, status, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7)
        RETURNING id
        """,
        reporter_uid, reported_uid, reported_listing_id, reported_swap_id,
        report_type, description, datetime.utcnow()
    )
    return result


# ============================================
# SCENARIO BUILDERS
# Create complete test scenarios with multiple related entities
# ============================================

async def create_swap_scenario(pool, category_a: str = "homes", category_b: str = "homes") -> dict:
    """
    Create a complete swap scenario: 2 users, 2 listings, 1 swap

    Returns:
        dict: {
            "user_a": str,
            "user_b": str,
            "listing_a": str,
            "listing_b": str,
            "swap_id": str
        }

    Example:
        scenario = await create_swap_scenario(pool, "homes", "books")
        user_a = scenario["user_a"]
        swap_id = scenario["swap_id"]
    """
    user_a = await add_user(pool, name="User A")
    user_b = await add_user(pool, name="User B")
    listing_a = await add_listing(pool, user_a, category_a, title=f"User A's {category_a}")
    listing_b = await add_listing(pool, user_b, category_b, title=f"User B's {category_b}")
    swap_id = await add_swap(pool, user_a, user_b, listing_a, listing_b, category_a, category_b)

    return {
        "user_a": user_a,
        "user_b": user_b,
        "listing_a": listing_a,
        "listing_b": listing_b,
        "swap_id": swap_id,
        "category_a": category_a,
        "category_b": category_b
    }
