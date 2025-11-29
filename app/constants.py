"""
Application-wide constants for category management and database configuration.
"""

# Valid listing categories
LISTING_CATEGORIES = ["homes", "books", "clothes", "caravans"]

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
