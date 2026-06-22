"""
Application-wide constants for category management and database configuration.
"""

from typing import Literal, get_args

# Valid listing categories — single source of truth.
# ListingCategory is the typing form (use it for Literal annotations / Pydantic
# fields); LISTING_CATEGORIES is the runtime list, derived from it so the two
# can never drift apart.
ListingCategory = Literal["homes", "books", "clothes", "caravans"]
LISTING_CATEGORIES = list(get_args(ListingCategory))

# Valid table names (includes listings categories + supporting tables)
VALID_TABLE_NAMES = ["homes", "books", "clothes", "caravans", "users", "listings"]

# JSONB fields by table for query builder
JSONB_FIELDS_BY_TABLE = {
    "homes": {"amenities", "car_details"},
    "books": set(),
    "clothes": set(),
    "caravans": set(),
    "users": set(),
}

# Listing fields concatenated into the searchable text per category, used by the
# wishlist matcher to keyword-match new listings against active wishlists.
SEARCHABLE_FIELDS_BY_CATEGORY = {
    "books": ["title", "author", "description", "genre_tags"],
    "clothes": ["title", "brand", "color", "material", "description"],
    "caravans": ["title", "make", "model", "description"],
    "homes": ["title", "description"],
}

# Guard against silent drift: every listing category must have searchable fields,
# otherwise wishlist keyword matching for that category would quietly never match.
_missing_searchable = set(LISTING_CATEGORIES) - set(SEARCHABLE_FIELDS_BY_CATEGORY)
assert not _missing_searchable, (
    f"SEARCHABLE_FIELDS_BY_CATEGORY is missing categories: {_missing_searchable}. "
    "Add them or wishlist matching will silently fail for those categories."
)
