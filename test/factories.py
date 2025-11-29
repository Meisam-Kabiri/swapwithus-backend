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
