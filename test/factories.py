import io

from fastapi import UploadFile
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use
from pydantic import BaseModel
from starlette.datastructures import Headers

from app.models.book_listing import BookListingCreate, BookListingResponse
from app.models.home_listing import HomeListingCreate, HomeListingResponse
from app.models.caravan_listing import CaravanListingCreate, CaravanListingResponse
from app.models.clothing_listing import ClothingListingCreate, ClothingListingResponse
from app.models.image import ImageMetadataCollection, ImageMetadataItem
from app.models.user import UserCreate
from uuid import uuid4
from faker import Faker
fake = Faker()


class UserCreateFactory(ModelFactory[UserCreate]):
    """Factory for generating fake UserCreate data"""

    __model__ = UserCreate
    __check_model__ = False  # Suppress deprecation warning

    # Tell polyfactory how to generate EmailStr
    email = Use(lambda: f"user{uuid4().hex}@example.com")

    # Generate realistic Firebase UID
    owner_firebase_uid = Use(
        lambda: f"firebase_uid_{ModelFactory.__random__.randint(100000, 999999)}"
    )


class HomeListingCreateFactory(ModelFactory[HomeListingCreate]):
    """Factory for generating fake HomeListingCreate data"""

    __model__ = HomeListingCreate
    __check_model__ = False  # Suppress deprecation warning

    # Constrain fields to fit database VARCHAR limits
    postal_code = Use(lambda: f"{ModelFactory.__random__.randint(10000, 99999)}")  # max 20 chars
    country = Use(lambda: f"Country{ModelFactory.__random__.randint(1, 99)}")  # max 100 chars
    city = Use(lambda: f"City{ModelFactory.__random__.randint(1, 999)}")  # max 100 chars
    surroundings_type = Use(lambda: f"Type{ModelFactory.__random__.randint(1, 9)}")  # max 30 chars
    title = Use(
        lambda: f"Test Home Listing {ModelFactory.__random__.randint(1, 999)}"
    )  # max 200 chars
    name = Use(lambda: f"Test User {ModelFactory.__random__.randint(1, 999)}")  # max 100 chars

class HomeListingUpdateCreateFactoryDict:
    """Only Generate some fields for Home fileds for update testing purpose"""
    def __init__(self):
        self.country = fake.country()  # max 100 chars
        self.city = fake.city()  # max 100 chars
        self.postal_code = fake.postcode()  # max 20 chars
        self.surroundings_type = fake.word()  # max 30 chars
        self.title = fake.sentence(nb_words=6)  # max 200 chars
        self.name = fake.name()  # max 100 chars
       
    def build_updated_data(self):
      return {
          "country": self.country,
          "city": self.city,
          "postal_code": self.postal_code,
          "surroundings_type": self.surroundings_type,
          "title": self.title,
          "name": self.name
      }
      

    def build_image_metadata(self, files_num):
        fake_meta_data = [
          ImageMetadataItem(caption=fake.sentence(nb_words=3), tag=fake.word(), is_hero=(i == 0), sort_order=i, public_url="", cdn_url="")
          for i in range(files_num)]
        return [ item.model_dump() for item in fake_meta_data]
          
    def build_data_form(self):
        return {
            "country": self.country,
            "city": self.city,
            "postal_code": self.postal_code,
            "surroundings_type": self.surroundings_type,
            "title": self.title,
            "name": self.name
        }


    # Constrain fields to fit database VARCHAR limits
    postal_code = Use(lambda: f"{ModelFactory.__random__.randint(10000, 99999)}")  # max 20 chars
    country = Use(lambda: f"Country{ModelFactory.__random__.randint(1, 99)}")  # max 100 chars
    city = Use(lambda: f"City{ModelFactory.__random__.randint(1, 999)}")  # max 100 chars
    surroundings_type = Use(lambda: f"Type{ModelFactory.__random__.randint(1, 9)}")  # max 30 chars
    title = Use(
        lambda: f"Test Home Listing {ModelFactory.__random__.randint(1, 999)}"
    )  # max 200 chars
    name = Use(lambda: f"Test User {ModelFactory.__random__.randint(1, 999)}")  # max 100 chars
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


class CaravanListingCreateFactory(ModelFactory[CaravanListingCreate]):
    """Factory for generating fake CaravanListingCreate data"""

    __model__ = CaravanListingCreate
    __check_model__ = False  # Suppress deprecation warning
    

class CaravanListingResponseFactory(ModelFactory[CaravanListingResponse]):
    """Factory for generating fake CaravanListingResponse data"""

    __model__ = CaravanListingResponse
    __check_model__ = False  # Suppress deprecation warning

class ClothingListingCreateFactory(ModelFactory[ClothingListingCreate]):
    """Factory for generating fake ClothingListingCreate data"""

    __model__ = ClothingListingCreate
    __check_model__ = False  # Suppress deprecation warning
    
class ClothingListingResponseFactory(ModelFactory[ClothingListingResponse]):
    """Factory for generating fake ClothingListingResponse data"""

    __model__ = ClothingListingResponse
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
            file=io.BytesIO(file.content),
            headers=Headers({"content-type": file.content_type}),
        )
        files.append(upload_file)
    return files


# test HomeListingResponseFactory
import pprint

obj = HomeListingResponseFactory.build()
pprint.pprint(obj)
