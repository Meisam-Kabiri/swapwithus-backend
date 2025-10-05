import json

from sqlalchemy import insert
import asyncpg
from db_connection.connection_to_db import get_db_pool

class DbManager:
      @staticmethod
      async def create_record_in_table(pool: asyncpg.Pool, data: dict, table_name: str) -> str:
          """
          Insert record from dict into specified table, return its ID
          """
          # Whitelist table names
          if table_name not in ['homes', 'users']:
              raise ValueError(f"Invalid table: {table_name}")

          # Convert lists/dicts to JSON strings for JSONB columns
          processed_data = {}
          for key, value in data.items():
              if isinstance(value, (list, dict)):
                  processed_data[key] = json.dumps(value)
              else:
                  processed_data[key] = value

          columns = ', '.join(processed_data.keys())
          placeholders = ', '.join([f'${i+1}' for i in range(len(processed_data))])
          values = list(processed_data.values())

          query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING *"

          async with pool.acquire() as conn:
              try:
                  await conn.execute(query, *values)
              except Exception as e:
                  print(f"❌ Error inserting record into {table_name}: {e}")
                  raise


      @staticmethod              
      async def update_record_in_table(pool: asyncpg.Pool,  data: dict, table_name: str, where_column: str, where_value: str, ) -> None:
          """
          Update record by ID in specified table with data from dict
          """
          if table_name not in ['homes', 'listings', 'users']:
              raise ValueError(f"Invalid table: {table_name}")

          set_clauses = []
          values = []
          for i, (key, value) in enumerate(data.items()):
              if isinstance(value, (list, dict)):
                  value = json.dumps(value)
              set_clauses.append(f"{key} = ${i+1}")
              values.append(value)
          set_clauses.append(f"updated_at = NOW()")
          set_statement = ', '.join(set_clauses)
          values.append(where_value)  # ID is the last parameter
          query = f"UPDATE {table_name} SET {set_statement} WHERE {where_column} = ${len(values)}"

          async with pool.acquire() as conn:
              try:
                  await conn.execute(query, *values)
              except Exception as e:
                  print(f"❌ Error updating record in {table_name}: {e}")
                  raise

# The method builds this SQL:
  # """
  # INSERT INTO homes (listing_id, title, city, maxGuests) 
  # VALUES ($1, $2, $3, $4) 
  # RETURNING listing_id
  # """

  # Different databases use different placeholders:

  # - PostgreSQL: $1, $2, $3
  # - MySQL: ?, ?, ?
  # - SQLite: ?, ?, ?
  # - Oracle: :1, :2, :3


  # This is:
  # - ✅ Safe from SQL injection (parameterized $1, $2, $3)
  # - ✅ Simple and readable
  # - ✅ Fast (direct asyncpg)
  # - ✅ No extra dependencies
