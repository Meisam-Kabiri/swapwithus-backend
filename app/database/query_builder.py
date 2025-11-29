import json

from app.constants import JSONB_FIELDS_BY_TABLE, LISTING_CATEGORIES, VALID_TABLE_NAMES


class QueryBuilder:
    # Import JSONB fields from centralized constants
    JSONB_FIELDS_BY_TABLE = JSONB_FIELDS_BY_TABLE

    @staticmethod
    def build_insert_query(data: dict, table_name: str) -> tuple[str, list]:
        """
        Build INSERT query and values from dict.
        Does NOT execute - returns query and values for the caller to execute.

        Args:
            data: Dictionary of column names and values
            table_name: Name of the table to insert into

        Returns:
            Tuple of (query_string, values_list)

        Example:
            query, values = DbManager.build_insert_query({"name": "John"}, "users")
            await conn.execute(query, *values)
        """
        # Whitelist table names
        if table_name not in VALID_TABLE_NAMES:
            raise ValueError(f"Invalid table: {table_name}")

        jsonb_fields = QueryBuilder.JSONB_FIELDS_BY_TABLE[table_name]

        # Convert lists/dicts to JSON strings for JSONB columns
        # But keep arrays as lists for TEXT[] columns (like genre_tags)
        processed_data = {}
        for key, value in data.items():
            # Don't convert lists for books table (genre_tags is TEXT[], not JSONB)
            if key in jsonb_fields and value is not None:
                processed_data[key] = json.dumps(value)  # serialize JSONB
            else:
                processed_data[key] = value

        columns = ", ".join(processed_data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(processed_data))])
        values = list(processed_data.values())

        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        return query, values

    @staticmethod
    def build_update_query(
        data: dict,
        table_name: str,
        where_column: str,
        where_value: str,
    ) -> tuple[str, list]:
        """
        Build UPDATE query and values from dict.
        Does NOT execute - returns query and values for the caller to execute.

        Args:
            data: Dictionary of column names and values to update
            table_name: Name of the table to update
            where_column: Column name for WHERE clause
            where_value: Value for WHERE clause

        Returns:
            Tuple of (query_string, values_list)

        Example:
            query, values = DbManager.build_update_query(
                {"name": "John"}, "users", "id", "123"
            )
            await conn.execute(query, *values)
        """
        if table_name not in VALID_TABLE_NAMES:
            raise ValueError(f"Invalid table: {table_name}")

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(data.items()):
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            set_clauses.append(f"{key} = ${i+1}")
            values.append(value)
        set_clauses.append("updated_at = NOW()")
        set_statement = ", ".join(set_clauses)
        values.append(where_value)  # WHERE value is the last parameter
        query = f"UPDATE {table_name} SET {set_statement} WHERE {where_column} = ${len(values)}"

        return query, values

    @staticmethod
    def build_get_listings_by_owner_id_query(
        table_name: str, gcloud_folder_name: str = None
    ) -> str:
        """
        Returns a parameterized SQL query string to fetch all listings from the specified table
        for a given owner_firebase_uid with images aggregated as JSON array.

        This avoids N+1 queries and prevents duplicate listing data by aggregating images
        into a single JSON array per listing.

        Args:
            table_name: Name of the table to query (e.g., "homes", "books", "clothes", "caravans").
            gcloud_folder_name: Optional folder name in GCS (defaults to table_name).

        Returns:
            A SQL query string with placeholders: $1 = owner_firebase_uid, $2 = token_prefix.
        """
        if table_name not in LISTING_CATEGORIES:
            raise ValueError(f"Invalid table: {table_name}")

        if gcloud_folder_name is None:
            gcloud_folder_name = table_name

        # Get singular category name (homes -> home, books -> book)
        category = table_name

        query = f"""
                SELECT
                    l.*,
                    '{category}' as category,
                    json_agg(
                        json_build_object(
                            'public_url', i.public_url,
                            'cdn_url', 'https://cdn.swapwithus.com/{gcloud_folder_name}/' ||
                                split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{gcloud_folder_name}/', 2) ||
                                '?' || $2,
                            'tag', i.tag,
                            'caption', i.caption,
                            'is_hero', i.is_hero,
                            'sort_order', i.sort_order
                        ) ORDER BY i.sort_order
                    ) AS images
                FROM {table_name} l
                LEFT JOIN images i ON i.listing_id = l.listing_id
                WHERE l.owner_firebase_uid = $1
                GROUP BY l.listing_id
                ORDER BY l.created_at DESC;
                """

        return query

    @staticmethod
    def build_query_get_listing_by_listingid_and_category(listing_id: str, category: str) -> str:
        """
        Returns a parameterized SQL query string to fetch a single listing from the specified table
        by listing_id with images aggregated as JSON array.

        This avoids N+1 queries and prevents duplicate listing data by aggregating images
        into a single JSON array per listing.

        Args:
            listing_id: The listing ID to query.
            category: Name of the table to query (e.g., "homes", "books", "clothes", "caravans").

        Returns:
            A SQL query string with placeholders: $1 = listing_id, $2 = token_prefix.
        """
        if category not in LISTING_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        # Get singular category name (homes -> home, books -> book)
        singular_category = category.rstrip("s")

        query = f"""
                SELECT
                    l.*,
                    '{singular_category}' as category,
                    json_agg(
                        json_build_object(
                            'public_url', i.public_url,
                            'signed_url', 'https://cdn.swapwithus.com/{category}/' ||
                                split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{category}/', 2) ||
                                '?' || $2,
                            'tag', i.tag,
                            'caption', i.caption,
                            'is_hero', i.is_hero,
                            'sort_order', i.sort_order
                        ) ORDER BY i.sort_order
                    ) AS images
                FROM {category} l
                LEFT JOIN images i ON i.listing_id = l.listing_id
                WHERE l.listing_id = $1
                GROUP BY l.listing_id;
                """

        return query
