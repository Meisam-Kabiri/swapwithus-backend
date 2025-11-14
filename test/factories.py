import io
from fastapi import UploadFile
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use
from pydantic import BaseModel

from app.models.user import UserCreate
from app.models.home_listing import HomeListingCreate, HomeListingResponse
from app.models.book_listing import BookListingCreate, BookListingResponse
from app.models.image import ImageMetadataItem, ImageMetadataCollection


class UserCreateFactory(ModelFactory[UserCreate]):
    """Factory for generating fake UserCreate data"""

    __model__ = UserCreate
    __check_model__ = False  # Suppress deprecation warning

    # Tell polyfactory how to generate EmailStr
    email = Use(lambda: f"user{ModelFactory.__random__.randint(1000, 9999)}@example.com")

    # Generate realistic Firebase UID
    owner_firebase_uid = Use(
        lambda: f"firebase_uid_{ModelFactory.__random__.randint(100000, 999999)}"
    )



class HomeListingCreateFactory(ModelFactory[HomeListingCreate]):
    """Factory for generating fake HomeListingCreate data"""

    __model__ = HomeListingCreate
    __check_model__ = False  # Suppress deprecation warning
    
class HomeListingResponseFactory(ModelFactory[HomeListingResponse]):
    """Factory for generating fake HomeListingResponse data"""

    __model__ = HomeListingResponse
    __check_model__ = False  # Suppress deprecation warning
    
class BookListingCreateFactory(ModelFactory[BookListingCreate]):
    """Factory for generating fake BookListingCreate data"""

    __model__ = BookListingCreate
    __check_model__ = False  # Suppress deprecation warning

    # Constrain title and author to fit VARCHAR(100)
    title = Use(lambda: f"Book Title {ModelFactory.__random__.randint(1, 999)}")
    author = Use(lambda: f"Author Name {ModelFactory.__random__.randint(1, 999)}")

    
    
class BookListingResponseFactory(ModelFactory[BookListingResponse]):
    """Factory for generating fake BookListingResponse data"""

    __model__ = BookListingResponse
    __check_model__ = False  # Suppress deprecation warning
    
    
class ImageMetadataItemFactory(ModelFactory[ImageMetadataItem]):
    """Factory for generating fake ImageMetadataItem data"""

    __model__ = ImageMetadataItem
    __check_model__ = False  # Suppress deprecation warning 
    
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
    __check_model__ = False

    filename = Use(lambda: f"test_image_{ModelFactory.__random__.randint(1, 999)}.jpg")
    content = Use(lambda: f"fake image content {ModelFactory.__random__.randint(1, 999)}".encode())
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
            file=io.BytesIO(file.content)
        )
        files.append(upload_file)
    return files
