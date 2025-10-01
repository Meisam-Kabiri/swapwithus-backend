"""
SwapWithUs Database Schema
Your existing table definitions with enhancements
"""

import os
import urllib.parse
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, DateTime, Boolean, Text,
    func, DECIMAL, DATE, UUID, ARRAY, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
import asyncpg
import asyncio
import json
from typing import Dict, List, Optional, Any
from uuid import uuid4

from .connection_to_db import get_db_connection  # Adjust import path

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your existing metadata and table definitions
metadata = MetaData()

# Users table (your existing code)
users_table = Table('users', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    # ... rest of your existing users table
)

# Listings table (your existing code with FK constraints added)
listings_table = Table('listings', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('listing_uuid', UUID, nullable=False, unique=True, server_default=func.gen_random_uuid()),
    Column('owner_id', Integer, ForeignKey('users.id'), nullable=False),  # Add FK
    # ... rest of your existing columns
    Column('last_modified_by', Integer, ForeignKey('users.id')),          # Add FK
)

# Your existing functions
async def create_users_table():
    # Your existing implementation
    pass

async def create_listings_table():
    # Your existing implementation + enhanced indexes
    pass

async def create_enhanced_indexes():
    # The additional indexes I suggested
    pass

2. lib/database/repositories/listings.py (Database operations)

# lib/database/repositories/listings.py
"""
SwapWithUs Listings Repository
High-performance database operations using asyncpg
"""

import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date
import asyncpg

class ListingsRepository:
    """High-performance listings operations using pure asyncpg"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_listing(self, listing_data: Dict[str, Any]) -> Dict[str, Any]:
        """CREATE: Insert new listing with JSON category data"""
        query = """
        INSERT INTO listings (
            owner_id, firebase_uid, title, description, category, condition,
            city, country, address, contact_name, contact_email, contact_phone,
            category_data, photos, preferred_swap_categories, value_estimate,
            latitude, longitude, created_by_ip, search_tags
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        RETURNING id, listing_uuid, created_at
        """

        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchrow(
                    query,
                    listing_data['owner_id'],
                    listing_data.get('firebase_uid'),
                    listing_data['title'],
                    listing_data['description'],
                    listing_data['category'],
                    listing_data.get('condition', 'good'),
                    listing_data['city'],
                    listing_data['country'],
                    listing_data.get('address'),
                    listing_data['contact_name'],
                    listing_data['contact_email'],
                    listing_data.get('contact_phone'),
                    json.dumps(listing_data.get('category_data', {})),
                    listing_data.get('photos', []),
                    listing_data.get('preferred_swap_categories', []),
                    listing_data.get('value_estimate'),
                    listing_data.get('latitude'),
                    listing_data.get('longitude'),
                    listing_data.get('created_by_ip'),
                    listing_data.get('search_tags', [])
                )
                return dict(result)
            except Exception as e:
                logger.error(f"❌ Create listing failed: {e}")
                raise

    # Add all the other methods (get, search, update, delete, etc.)
    # ... (use the repository code I showed earlier)
