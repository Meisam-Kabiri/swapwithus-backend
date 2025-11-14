import json

import asyncpg  # type: ignore


class QueryBuilder:
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
        if table_name not in ["homes", "users", "books"]:
            raise ValueError(f"Invalid table: {table_name}")

        # Convert lists/dicts to JSON strings for JSONB columns
        # But keep arrays as lists for TEXT[] columns (like genre_tags)
        processed_data = {}
        for key, value in data.items():
            # Don't convert lists for books table (genre_tags is TEXT[], not JSONB)
            if isinstance(value, dict) or (isinstance(value, list) and table_name != "books"):
                processed_data[key] = json.dumps(value)
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
        if table_name not in ["homes", "listings", "users", "books"]:
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
