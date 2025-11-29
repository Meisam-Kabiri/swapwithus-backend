"""
Utility functions for models
"""

from pydantic import BaseModel, create_model


def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase"""
    first, *rest = snake_str.split("_")
    return first + "".join(x.title() for x in rest)


def make_partial(model: type[BaseModel]) -> type[BaseModel]:
    """
    Create a partial version of a Pydantic model where all fields are optional.
    Useful for update/patch operations where only changed fields are sent.

    Args:
        model: type[BaseModel] - The Pydantic model class to make partial (not an instance, the class itself)

    Returns:
        type[BaseModel] - A new Pydantic model class with all fields optional

    Example:
        HomeListingUpdate = make_partial(HomeListingCreate)
    """
    # fields: dict - Will store field definitions for the new model
    fields = {}

    # model.model_fields: dict - Pydantic's dict of all fields in the model (field_name -> FieldInfo)
    for field_name, field_info in model.model_fields.items():
        # field_name: str - Name of the field (e.g., "owner_firebase_uid")
        # field_info: FieldInfo - Pydantic object containing field metadata (type, default, validators, etc.)
        # field_info.annotation: type - The original type annotation (e.g., str, int, Literal["value"])

        # Create new field: (type, default_value)
        # field_info.annotation | None - Union type: original type OR None (Python 3.10+ syntax)
        # None - Default value for the field (makes it optional)
        fields[field_name] = (field_info.annotation | None, None)

    # create_model: Pydantic function - Dynamically creates a new Pydantic model class at runtime
    # f'{model.__name__}Update': str - Name for new class (e.g., "HomeListingCreateUpdate")
    # __config__=model.model_config: ConfigDict - Copy configuration from original model
    # **fields: dict - Unpack field definitions as keyword arguments
    return create_model(f"{model.__name__}Update", __config__=model.model_config, **fields)
