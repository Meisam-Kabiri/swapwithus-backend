from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use

from app.models.user import UserCreate


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


# # Use it
# user = UserCreateFactory.build()
