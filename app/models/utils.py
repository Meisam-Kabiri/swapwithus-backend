"""
Utility functions for models
"""


def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase"""
    first, *rest = snake_str.split("_")
    return first + "".join(x.title() for x in rest)
