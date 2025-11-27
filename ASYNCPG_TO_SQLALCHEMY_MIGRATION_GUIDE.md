# AsyncPG to SQLAlchemy Migration Guide

## Current Architecture Overview

Our SwapWithUs backend currently uses **pure asyncpg** for all database operations. This is a deliberate architectural choice documented in `app/database/connection.py`:

```
SPEED + SECURITY focused architecture for swap platform:
- asyncpg connection pool for ALL database operations
- faster than SQLAlchemy async engine
- Critical for high-frequency swap transactions
- Direct PostgreSQL protocol, minimal overhead
- Production-grade connection pooling
```

### Current Stack
- **Driver**: `asyncpg==0.30.0` (pure async PostgreSQL driver)
- **Query Style**: Raw parameterized SQL with custom `QueryBuilder`
- **Connection Management**: asyncpg connection pool (`asyncpg.Pool`)
- **Note**: SQLAlchemy is already in `requirements.txt` (`SQLAlchemy==2.0.44`) but **NOT USED**

---

## ORM vs Core: Which Level of SQLAlchemy Do We Need?

### Short Answer: **Core (Engine-level) Only**

Based on our codebase analysis:

| Factor | our Current Code | Recommendation |
|--------|-------------------|----------------|
| Query complexity | Raw SQL with parameterized placeholders | Core is sufficient |
| Relationships | No ORM-style relationships, manual JOINs | Core is sufficient |
| Models | Pydantic schemas only, no ORM models | Core is sufficient |
| Transactions | Explicit `conn.transaction()` blocks | Core supports this |
| JSON handling | Manual `json.dumps()` in QueryBuilder | Core handles natively |
| Performance need | "High-frequency swap transactions" | Core has less overhead than ORM |

### Why NOT Full ORM?

1. **No ORM models exist** - We use Pydantic schemas (`app/schemas/`) for validation, not SQLAlchemy ORM models
2. **Raw SQL everywhere** - our `QueryBuilder` generates raw SQL strings
3. **Performance-critical** - ORM adds object mapping overhead
4. **No relationship traversal** - We manually JOIN tables
5. **Migration effort** - ORM requires rewriting all data access patterns

### What We'd Need from SQLAlchemy:

- **Async Engine** (`create_async_engine`)
- **Async Session** (optional, for transaction management)
- **Connection Pool** (built into engine)
- **Text queries** (`text()` for parameterized raw SQL)

---

## Files That Need Changes (With SQLAlchemy Implementation)

### 1. `app/database/connection.py` (MAJOR CHANGES)

**Current asyncpg Code:**
```python
import asyncpg

_db_pool: asyncpg.Pool | None = None

async def create_asyncpg_pool():
    return await asyncpg.create_pool(
        ASYNCPG_URL,
        min_size=0,
        max_size=50,
        command_timeout=60,
    )

def get_pool() -> asyncpg.Pool:
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return _db_pool

async def get_db_connection() -> asyncpg.Connection:
    return await asyncpg.connect(ASYNCPG_URL)
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Change URL format: add +asyncpg driver
# Before: postgresql://user:pass@host/db
# After:  postgresql+asyncpg://user:pass@host/db
SQLALCHEMY_URL = ASYNCPG_URL.replace("postgresql://", "postgresql+asyncpg://")

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None

async def create_engine():
    """Create SQLAlchemy async engine with connection pool"""
    global _engine, _async_session_factory

    _engine = create_async_engine(
        SQLALCHEMY_URL,
        pool_size=5,           # Equivalent to min_size
        max_overflow=45,       # pool_size + max_overflow = 50 (like max_size=50)
        pool_timeout=60,       # Equivalent to command_timeout
        pool_pre_ping=True,    # Health check connections
        echo=False,            # Set True for SQL logging
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return _engine

def get_engine() -> AsyncEngine:
    """Get engine with runtime check"""
    if _engine is None:
        raise RuntimeError("Database engine not initialized")
    return _engine

def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get session factory for transaction-based operations"""
    if _async_session_factory is None:
        raise RuntimeError("Session factory not initialized")
    return _async_session_factory

async def get_db_connection():
    """Get a raw connection for migrations"""
    return await get_engine().connect()
```

**Why these changes:**
- SQLAlchemy uses engines with built-in pooling, not separate pools
- `pool_size` + `max_overflow` replaces `min_size`/`max_size`
- Session factory provides cleaner transaction management
- URL needs `+asyncpg` driver suffix

---

### 2. `app/database/query_builder.py` (MODERATE CHANGES)

**Current asyncpg Code:**
```python
class QueryBuilder:
    @staticmethod
    def build_insert_query(data: dict, table_name: str) -> tuple[str, list]:
        # ...
        placeholders = ", ".join([f"${i+1}" for i in range(len(processed_data))])
        values = list(processed_data.values())
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return query, values  # Returns (query, list)

    @staticmethod
    def build_update_query(data, table_name, where_column, where_value) -> tuple[str, list]:
        # ...
        set_clauses.append(f"{key} = ${i+1}")
        # ...
        query = f"UPDATE {table_name} SET {set_statement} WHERE {where_column} = ${len(values)}"
        return query, values
```

**SQLAlchemy Implementation:**
```python
import json

class QueryBuilder:
    @staticmethod
    def build_insert_query(data: dict, table_name: str) -> tuple[str, dict]:
        """
        Build INSERT query with named parameters for SQLAlchemy.
        Returns (query_string, params_dict) instead of (query_string, values_list)
        """
        if table_name not in ["homes", "users", "books", "clothes", "caravans"]:
            raise ValueError(f"Invalid table: {table_name}")

        # Convert lists/dicts to JSON strings for JSONB columns
        processed_data = {}
        for key, value in data.items():
            if isinstance(value, dict) or (isinstance(value, list) and table_name != "books"):
                processed_data[key] = json.dumps(value)
            else:
                processed_data[key] = value

        columns = ", ".join(processed_data.keys())
        # Change: $1, $2 -> :col1, :col2 (named parameters)
        placeholders = ", ".join([f":{key}" for key in processed_data.keys()])

        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        return query, processed_data  # Returns dict, not list

    @staticmethod
    def build_update_query(
        data: dict,
        table_name: str,
        where_column: str,
        where_value: str,
    ) -> tuple[str, dict]:
        """Build UPDATE query with named parameters for SQLAlchemy."""
        if table_name not in ["homes", "listings", "users", "books", "clothes", "caravans"]:
            raise ValueError(f"Invalid table: {table_name}")

        params = {}
        set_clauses = []

        for key, value in data.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            # Change: $1 -> :key (named parameter)
            set_clauses.append(f"{key} = :{key}")
            params[key] = value

        set_clauses.append("updated_at = NOW()")
        set_statement = ", ".join(set_clauses)

        # Add WHERE parameter
        params["where_value"] = where_value
        query = f"UPDATE {table_name} SET {set_statement} WHERE {where_column} = :where_value"

        return query, params

    @staticmethod
    def build_get_listings_by_owner_id_query(table_name: str, gcloud_folder_name: str = None) -> str:
        """Same as before - just change $1, $2 to :uid, :token"""
        if table_name not in ["homes", "books", "clothes", "caravans"]:
            raise ValueError(f"Invalid table: {table_name}")

        if gcloud_folder_name is None:
            gcloud_folder_name = table_name

        category = table_name.rstrip('s')

        # Change: $1 -> :uid, $2 -> :token
        query = f"""
            SELECT
                l.*,
                '{category}' as category,
                json_agg(
                    json_build_object(
                        'public_url', i.public_url,
                        'cdn_url', 'https://cdn.swapwithus.com/{gcloud_folder_name}/' ||
                            split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{gcloud_folder_name}/', 2) ||
                            '?' || :token,
                        'tag', i.tag,
                        'caption', i.caption,
                        'is_hero', i.is_hero,
                        'sort_order', i.sort_order
                    ) ORDER BY i.sort_order
                ) AS images
            FROM {table_name} l
            LEFT JOIN images i ON i.listing_id = l.listing_id
            WHERE l.owner_firebase_uid = :uid
            GROUP BY l.listing_id
            ORDER BY l.created_at DESC;
        """
        return query
```

**Key differences:**
| Aspect | asyncpg | SQLAlchemy |
|--------|---------|------------|
| Placeholders | `$1, $2, $3` | `:param1, :param2` |
| Return type | `(query, list)` | `(query, dict)` |
| Parameter passing | `*values` (positional) | `dict` (named) |

---

### 3. `app/main.py` (MODERATE CHANGES)

**Current asyncpg Code:**
```python
import app.database.connection as db_connection
from app.database.connection import create_asyncpg_pool, get_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_connection._db_pool = await create_asyncpg_pool()
    logger.info("Database pool created at startup")

    yield  # App runs

    # Shutdown
    if db_connection._db_pool:
        await db_connection._db_pool.close()
        logger.info("Database pool closed")
```

**SQLAlchemy Implementation:**
```python
import app.database.connection as db_connection
from app.database.connection import create_engine, get_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_engine()
    logger.info("SQLAlchemy engine created at startup")

    yield  # App runs

    # Shutdown
    engine = get_engine()
    if engine:
        await engine.dispose()
        logger.info("SQLAlchemy engine disposed")
```

**Why:**
- `create_engine()` replaces `create_asyncpg_pool()`
- `engine.dispose()` replaces `pool.close()`

---

### 4. `app/api/users.py` (SIGNIFICANT CHANGES)

**Current asyncpg Code:**
```python
from app.database.connection import get_pool

# GET - fetchrow (single row)
@router.get("/me")
async def get_my_user_data(request: Request):
    uid = extract_firebase_user_uid(request)
    query = """
        SELECT owner_firebase_uid, email, name, profile_image, ...
        FROM users WHERE owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)

# POST - execute (insert)
@router.post("")
async def create_user(request: Request, user: UserCreate):
    insert_query, insert_values = QueryBuilder.build_insert_query(user_dict, "users")
    async with get_pool().acquire() as conn:
        await conn.execute(insert_query, *insert_values)

# DELETE - fetchval + execute with result check
@router.delete("/{uid}")
async def delete_user(request: Request, uid: str):
    async with get_pool().acquire() as conn:
        exist_user = await conn.fetchval(
            "SELECT 1 FROM users WHERE owner_firebase_uid = $1", uid
        )
        async with conn.transaction():
            image_urls = await conn.fetch(
                "SELECT public_url FROM images WHERE owner_firebase_uid = $1", uid
            )
            result = await conn.execute("DELETE FROM users WHERE owner_firebase_uid = $1", uid)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="User not found")

# PATCH - execute with result check
@router.patch("/{uid}")
async def update_user(request: Request, uid: str, user: UserUpdate):
    async with get_pool().acquire() as conn:
        result = await conn.execute(query, *values, uid)
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="User not found")
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy import text
from app.database.connection import get_engine

# GET - fetchrow -> execute().fetchone()
@router.get("/me")
async def get_my_user_data(request: Request):
    uid = extract_firebase_user_uid(request)
    query = text("""
        SELECT owner_firebase_uid, email, name, profile_image, ...
        FROM users WHERE owner_firebase_uid = :uid
    """)
    async with get_engine().connect() as conn:
        result = await conn.execute(query, {"uid": uid})
        user_row = result.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return user_row._asdict()  # or dict(user_row._mapping)

# POST - execute (insert)
@router.post("")
async def create_user(request: Request, user: UserCreate):
    insert_query, params = QueryBuilder.build_insert_query(user_dict, "users")
    async with get_engine().connect() as conn:
        await conn.execute(text(insert_query), params)
        await conn.commit()  # Must explicitly commit!

# DELETE - scalar + execute with rowcount check
@router.delete("/{uid}")
async def delete_user(request: Request, uid: str):
    async with get_engine().connect() as conn:
        # fetchval -> scalar()
        exist_user = (await conn.execute(
            text("SELECT 1 FROM users WHERE owner_firebase_uid = :uid"),
            {"uid": uid}
        )).scalar()

        async with conn.begin():  # Transaction
            # fetch -> fetchall()
            image_result = await conn.execute(
                text("SELECT public_url FROM images WHERE owner_firebase_uid = :uid"),
                {"uid": uid}
            )
            image_urls = image_result.fetchall()

            result = await conn.execute(
                text("DELETE FROM users WHERE owner_firebase_uid = :uid"),
                {"uid": uid}
            )
            # Change: "DELETE 0" -> result.rowcount
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")

# PATCH - execute with rowcount check
@router.patch("/{uid}")
async def update_user(request: Request, uid: str, user: UserUpdate):
    query = text("""
        UPDATE users SET name = :name, phone_country_code = :phone_country_code, ...
        WHERE owner_firebase_uid = :uid
    """)
    async with get_engine().connect() as conn:
        result = await conn.execute(query, {**user_dict, "uid": uid})
        await conn.commit()
        # Change: "UPDATE 0" -> result.rowcount
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
```

**Method Translation:**
| asyncpg | SQLAlchemy | Notes |
|---------|------------|-------|
| `conn.fetchrow(q, val)` | `(await conn.execute(text(q), {"p": val})).fetchone()` | Single row |
| `conn.fetch(q, val)` | `(await conn.execute(text(q), {"p": val})).fetchall()` | Multiple rows |
| `conn.fetchval(q, val)` | `(await conn.execute(text(q), {"p": val})).scalar()` | Single value |
| `conn.execute(q, *vals)` | `await conn.execute(text(q), params_dict)` | Write operation |
| `result == "DELETE 0"` | `result.rowcount == 0` | Check affected rows |
| `dict(row)` | `row._asdict()` or `row._mapping` | Convert to dict |

---

### 5. `app/api/homes.py` (SIGNIFICANT CHANGES)

**Current asyncpg Code:**
```python
async with get_pool().acquire() as conn:
    async with conn.transaction():
        # Insert user
        await conn.execute(
            create_user_query,
            user_data_dict.get("owner_firebase_uid"),
            user_data_dict.get("email"),
            user_data_dict.get("name"),
            user_data_dict.get("profile_image"),
        )

        # Insert listing
        insert_query, insert_values = QueryBuilder.build_insert_query(listing_data_dict, "homes")
        await conn.execute(insert_query, *insert_values)

        # Batch insert images
        image_data = [(rec["uid"], rec["listing_id"], ...) for rec in image_table_records]
        await conn.executemany(insert_images_query, image_data)
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy import text
from app.database.connection import get_engine

async with get_engine().connect() as conn:
    async with conn.begin():  # Transaction (replaces conn.transaction())
        # Insert user - use named params
        create_user_query = text("""
            INSERT INTO users (owner_firebase_uid, email, name, profile_image, created_at, updated_at)
            VALUES (:uid, :email, :name, :profile_image, NOW(), NOW())
            ON CONFLICT (owner_firebase_uid) DO NOTHING
        """)
        await conn.execute(create_user_query, {
            "uid": user_data_dict.get("owner_firebase_uid"),
            "email": user_data_dict.get("email"),
            "name": user_data_dict.get("name"),
            "profile_image": user_data_dict.get("profile_image"),
        })

        # Insert listing - QueryBuilder now returns dict
        insert_query, params = QueryBuilder.build_insert_query(listing_data_dict, "homes")
        await conn.execute(text(insert_query), params)

        # Batch insert images - executemany replacement
        insert_images_query = text("""
            INSERT INTO images (owner_firebase_uid, listing_id, category, public_url, tag, caption, is_hero, sort_order)
            VALUES (:uid, :listing_id, :category, :public_url, :tag, :caption, :is_hero, :sort_order)
        """)

        # Option 1: Loop (simpler, slightly slower)
        for record in image_table_records:
            await conn.execute(insert_images_query, {
                "uid": record["owner_firebase_uid"],
                "listing_id": record["listing_id"],
                "category": record["category"],
                "public_url": record["public_url"],
                "tag": record["tag"],
                "caption": record["caption"],
                "is_hero": record["is_hero"],
                "sort_order": record["sort_order"],
            })

        # Option 2: Bulk insert with list of dicts (faster)
        # await conn.execute(insert_images_query, [
        #     {"uid": r["owner_firebase_uid"], "listing_id": r["listing_id"], ...}
        #     for r in image_table_records
        # ])
```

**Key differences:**
| asyncpg | SQLAlchemy |
|---------|------------|
| `conn.transaction()` | `conn.begin()` |
| `conn.executemany(q, list_of_tuples)` | Loop with `conn.execute()` or pass list of dicts |
| Auto-commit on success | `conn.begin()` auto-commits on exit |

---

### 6. `app/api/listings.py` (SIGNIFICANT CHANGES)

**Current asyncpg Code:**
```python
async def fetch_category(category: str, token: str):
    async with get_pool().acquire() as conn:
        query = QueryBuilder.build_get_listings_by_owner_id_query(category)
        return await conn.fetch(query, uid, token)

# Parallel execution
homes, books, clothes, caravans = await asyncio.gather(
    fetch_category("homes", token),
    fetch_category("books", token),
    fetch_category("clothes", token),
    fetch_category("caravans", token),
)
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy import text
from app.database.connection import get_engine

async def fetch_category(category: str, token: str, uid: str):
    async with get_engine().connect() as conn:
        query = text(QueryBuilder.build_get_listings_by_owner_id_query(category))
        result = await conn.execute(query, {"uid": uid, "token": token})
        return result.fetchall()

# Parallel execution - same pattern works
homes, books, clothes, caravans = await asyncio.gather(
    fetch_category("homes", token, uid),
    fetch_category("books", token, uid),
    fetch_category("clothes", token, uid),
    fetch_category("caravans", token, uid),
)

# Convert rows to dicts
homes_list = [row._asdict() for row in homes]
```

---

### 7. `app/api/favorites.py` (MODERATE CHANGES)

**Current asyncpg Code:**
```python
# DELETE
remove_favorite_query = """
    DELETE FROM favorites WHERE owner_firebase_uid = $1 AND listing_id = $2
"""
async with get_pool().acquire() as conn:
    await conn.execute(remove_favorite_query, user_id, listing_id)

# INSERT
add_favorite_query = """
    INSERT INTO favorites (owner_firebase_uid, listing_id, created_at)
    VALUES ($1, $2, NOW()) ON CONFLICT DO NOTHING
"""
async with get_pool().acquire() as conn:
    await conn.execute(add_favorite_query, user_id, listing_id)

# SELECT
async with get_pool().acquire() as conn:
    favorite_rows = await conn.fetch(get_favorites_query, user_id)
    favorites = [dict(row) for row in favorite_rows]
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy import text
from app.database.connection import get_engine

# DELETE
remove_favorite_query = text("""
    DELETE FROM favorites WHERE owner_firebase_uid = :user_id AND listing_id = :listing_id
""")
async with get_engine().connect() as conn:
    await conn.execute(remove_favorite_query, {"user_id": user_id, "listing_id": listing_id})
    await conn.commit()

# INSERT
add_favorite_query = text("""
    INSERT INTO favorites (owner_firebase_uid, listing_id, created_at)
    VALUES (:user_id, :listing_id, NOW()) ON CONFLICT DO NOTHING
""")
async with get_engine().connect() as conn:
    await conn.execute(add_favorite_query, {"user_id": user_id, "listing_id": listing_id})
    await conn.commit()

# SELECT
async with get_engine().connect() as conn:
    result = await conn.execute(text(get_favorites_query), {"user_id": user_id})
    favorite_rows = result.fetchall()
    favorites = [row._asdict() for row in favorite_rows]
```

---

### 8. `app/api/common.py` (SIGNIFICANT CHANGES)

Same patterns as `homes.py` - transactions and batch inserts.

---

### 9. `test/conftest.py` (MODERATE CHANGES)

**Current asyncpg Code:**
```python
import app.database.connection as db_connection
from app.database.connection import ASYNCPG_URL, create_asyncpg_pool

@pytest_asyncio.fixture(scope="function")
async def create_db_pool():
    db_connection._db_pool = await create_asyncpg_pool()
    yield db_connection._db_pool
    await db_connection._db_pool.close()
```

**SQLAlchemy Implementation:**
```python
import app.database.connection as db_connection
from app.database.connection import SQLALCHEMY_URL, create_engine, get_engine

# Safety check update
if "localhost" not in SQLALCHEMY_URL and "127.0.0.1" not in SQLALCHEMY_URL:
    print(f"FATAL: Tests must connect to localhost")
    sys.exit(1)

@pytest_asyncio.fixture(scope="function")
async def create_db_engine():
    await create_engine()
    yield get_engine()
    await get_engine().dispose()
```

---

### 10. `migration/*.py` Files (MINIMAL CHANGES)

**Current asyncpg Code:**
```python
from app.database.connection import get_db_connection

async def run_migration():
    conn = await get_db_connection()
    await conn.execute(create_table_sql)
    await conn.close()
```

**SQLAlchemy Implementation:**
```python
from sqlalchemy import text
from app.database.connection import get_engine

async def run_migration():
    async with get_engine().connect() as conn:
        await conn.execute(text(create_table_sql))
        await conn.commit()
```

---

## Method Translation Reference

| asyncpg Method | SQLAlchemy Equivalent | Notes |
|----------------|----------------------|-------|
| `pool.acquire()` | `async_session()` or `engine.connect()` | Context manager |
| `conn.fetchrow(query, *args)` | `(await conn.execute(text(query), params)).fetchone()` | Returns `Row` not `Record` |
| `conn.fetch(query, *args)` | `(await conn.execute(text(query), params)).fetchall()` | Returns list of `Row` |
| `conn.fetchval(query, *args)` | `(await conn.execute(text(query), params)).scalar()` | Single value |
| `conn.execute(query, *args)` | `await conn.execute(text(query), params)` | Returns `CursorResult` |
| `conn.executemany(query, args_list)` | Loop or `conn.execute(stmt, list_of_dicts)` | Different syntax |
| `conn.transaction()` | `session.begin()` or `conn.begin()` | Transaction context |
| `result == "UPDATE 0"` | `result.rowcount == 0` | Check affected rows |

---

## Parameter Placeholder Translation

| asyncpg Style | SQLAlchemy Style |
|---------------|------------------|
| `$1, $2, $3` | `:param1, :param2, :param3` |
| `await conn.fetch(query, val1, val2)` | `await conn.execute(text(query), {"param1": val1, "param2": val2})` |

---

## Raw SQL (`text()`) vs SQLAlchemy Core Methods: Which Should We Use?

If we switch to SQLAlchemy, we have **two approaches**:

### Option A: Raw SQL with `text()` (Minimal Change)

Keep writing raw SQL strings, just wrap them in `text()`:

```python
from sqlalchemy import text

# Current asyncpg style:
query = "SELECT * FROM users WHERE owner_firebase_uid = $1"
user = await conn.fetchrow(query, uid)

# SQLAlchemy with text():
query = text("SELECT * FROM users WHERE owner_firebase_uid = :uid")
result = await conn.execute(query, {"uid": uid})
user = result.fetchone()
```

### Option B: SQLAlchemy Core Expression Language (Full Rewrite)

Use SQLAlchemy's programmatic query builders:

```python
from sqlalchemy import select, insert, update, delete
from sqlalchemy import Table, Column, String, MetaData

# Define table metadata
metadata = MetaData()
users = Table('users', metadata,
    Column('owner_firebase_uid', String(128), primary_key=True),
    Column('email', String(255)),
    # ... other columns
)

# SELECT query
query = select(users).where(users.c.owner_firebase_uid == uid)
result = await conn.execute(query)
user = result.fetchone()

# INSERT query
query = insert(users).values(owner_firebase_uid=uid, email=email)
await conn.execute(query)

# UPDATE query
query = update(users).where(users.c.owner_firebase_uid == uid).values(email=new_email)
await conn.execute(query)
```

---

### Comparison: `text()` vs Core Expression Language

| Aspect | `text()` (Raw SQL) | Core Expression Language |
|--------|-------------------|-------------------------|
| **Migration effort** | Low - just change placeholders | High - rewrite all queries |
| **Code readability** | Familiar SQL syntax | Pythonic, but verbose |
| **Type safety** | None | Compile-time column checks |
| **SQL injection safety** | Safe (parameterized) | Safe (auto-parameterized) |
| **IDE autocomplete** | No | Yes (column names) |
| **Database portability** | Low (raw SQL is DB-specific) | High (generates correct SQL per DB) |
| **Complex queries** | Easy (write any SQL) | Hard (JOINs, CTEs, window functions) |
| **Performance** | Slightly faster | Slight overhead from query building |
| **Learning curve** | None | Medium-High |

---

### Recommendation for Our Codebase: **Use `text()` (Raw SQL)**

**Reasons:**

1. **Our queries are PostgreSQL-specific anyway**
   - `json_agg()`, `json_build_object()` in `build_get_listings_by_owner_id_query()`
   - `split_part()` string functions
   - These don't translate to other databases

2. **Minimal migration effort**
   - Just change `$1` to `:param1`
   - Keep our existing `QueryBuilder` logic mostly intact

3. **Complex queries are easier in raw SQL**
   ```python
   # Our current query (from query_builder.py) - Easy in raw SQL:
   SELECT l.*, json_agg(json_build_object('public_url', i.public_url, ...))
   FROM homes l LEFT JOIN images i ON i.listing_id = l.listing_id
   WHERE l.owner_firebase_uid = $1
   GROUP BY l.listing_id

   # Same in SQLAlchemy Core - Much harder:
   from sqlalchemy import func, select
   query = (
       select(
           homes,
           func.json_agg(
               func.json_build_object(
                   'public_url', images.c.public_url,
                   # ... many more fields
               )
           ).label('images')
       )
       .select_from(homes.outerjoin(images, homes.c.listing_id == images.c.listing_id))
       .where(homes.c.owner_firebase_uid == bindparam('uid'))
       .group_by(homes.c.listing_id)
   )
   ```

4. **We don't need database portability**
   - We're committed to Cloud SQL PostgreSQL
   - No plans to support MySQL/SQLite

5. **QueryBuilder already generates safe parameterized queries**
   - No SQL injection risk with current approach
   - Core doesn't add safety, just different syntax

---

### When to Use Core Expression Language Instead

Use SQLAlchemy Core methods if:

- You want **IDE autocomplete** for column names
- You're building **dynamic queries** with many optional filters
- You need **database portability** (PostgreSQL → MySQL → SQLite)
- You want **schema validation** at query-build time
- Team prefers **Pythonic syntax** over raw SQL

---

### Hybrid Approach (Practical Middle Ground)

Use **both** in the same codebase:

| Query Type | Approach | Why |
|------------|----------|-----|
| Simple CRUD | Core `insert()`, `select()`, `update()` | Cleaner, type-safe |
| Complex JOINs | `text()` raw SQL | Easier to write and read |
| Aggregations | `text()` raw SQL | PostgreSQL-specific functions |
| Dynamic filters | Core with conditionals | Programmatic query building |

```python
# Simple insert - use Core
stmt = insert(users).values(**user_data)
await conn.execute(stmt)

# Complex aggregation - use text()
query = text("""
    SELECT l.*, json_agg(json_build_object(...)) as images
    FROM homes l LEFT JOIN images i ON ...
    WHERE l.owner_firebase_uid = :uid
    GROUP BY l.listing_id
""")
result = await conn.execute(query, {"uid": uid})
```

---

### Impact on Our QueryBuilder

**If using `text()` (Recommended):**

```python
# query_builder.py - Minimal changes
class QueryBuilder:
    @staticmethod
    def build_insert_query(data: dict, table_name: str) -> tuple[str, dict]:
        # Change from $1, $2 to :col1, :col2
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f":{key}" for key in data.keys()])
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return query, data  # Return dict instead of list
```

**If using Core Expression Language:**

```python
# query_builder.py - Complete rewrite needed
# Would need table definitions + completely different approach
# Essentially DELETE the entire QueryBuilder and use Core constructs directly
```

---

### Summary: `text()` vs Core

| If We Switch to SQLAlchemy... | Recommendation |
|------------------------------|----------------|
| **Approach** | Use `text()` with raw SQL |
| **Why** | Minimal changes, PostgreSQL-specific queries work |
| **QueryBuilder changes** | Just update placeholder syntax |
| **When to use Core** | Only for simple CRUD if desired |
| **Avoid Core for** | Complex JOINs, aggregations, PostgreSQL functions |

---

## Advantages of Switching to SQLAlchemy

### 1. **Database Portability**
- Easily switch between PostgreSQL, MySQL, SQLite for testing
- Unified API regardless of backend

### 2. **Query Building Safety**
- SQLAlchemy Core provides type-safe query construction
- No manual string concatenation (safer from SQL injection)

### 3. **Better ORM Option in Future**
- If we later want relationship mapping, it's already there
- Gradual migration path to ORM if needed

### 4. **Wider Ecosystem**
- More tutorials, documentation, Stack Overflow answers
- Integration with tools like Alembic for migrations

### 5. **Connection Pool Flexibility**
- Built-in pool configuration options
- Connection health checks, pre-ping, recycling

### 6. **Standardized Transaction Management**
- Session-based transactions are more intuitive
- Automatic rollback on exceptions

### 7. **Type Coercion**
- Automatic JSON/JSONB handling without manual `json.dumps()`
- Better datetime, UUID, array handling

---

## Disadvantages of Switching to SQLAlchemy

### 1. **Performance Overhead**
- asyncpg is **~2-3x faster** for raw queries
- SQLAlchemy adds abstraction layer overhead
- Critical for our "high-frequency swap transactions"

### 2. **Migration Effort**
- Every database call needs rewriting
- ~500+ lines of code changes across 8+ files
- Testing required for all endpoints

### 3. **Different Paradigm**
- Team must learn SQLAlchemy patterns
- Different debugging approach
- Different error messages

### 4. **PostgreSQL-Specific Features**
- asyncpg gives direct access to PostgreSQL features
- Some PostgreSQL-specific syntax may need workarounds

### 5. **Result Object Differences**
- asyncpg `Record` objects work like dicts naturally
- SQLAlchemy `Row` objects need `.mappings()` or attribute access
- May require changes in response serialization

### 6. **Existing QueryBuilder Works**
- our custom `QueryBuilder` already handles our needs
- SQLAlchemy would replace this with more code

### 7. **Unnecessary Complexity**
- We're not using ORM features
- Adding abstraction without clear benefit
- "If it ain't broke, don't fix it"

---

## Recommendation

### **Don't Switch** (for now)

**Reasons:**

1. **our architecture is intentionally optimized for asyncpg** - The comments explicitly state this is a conscious decision for performance

2. **No compelling reason to change** - SQLAlchemy is already in requirements.txt but unused, suggesting this was evaluated and rejected

3. **Cost vs Benefit**:
   - Cost: Days/weeks of migration + testing
   - Benefit: Portability we don't need (you're committed to Cloud SQL PostgreSQL)

4. **Performance matters for our use case** - "High-frequency swap transactions" benefit from asyncpg's speed

5. **Current code is clean** - our `QueryBuilder` pattern is safe and maintainable

### When Switching Would Make Sense:

- If we need to support multiple database backends
- If we want to gradually adopt ORM patterns
- If you're bringing on developers who only know SQLAlchemy
- If we need Alembic for migration management (though we have working migrations)

---

## If We Still Want to Switch

### Migration Order (Recommended):

1. **`app/database/connection.py`** - Set up SQLAlchemy engine
2. **`app/database/query_builder.py`** - Update placeholder syntax
3. **`test/conftest.py`** - Update test fixtures
4. **`app/api/favorites.py`** - Simplest API, good for testing pattern
5. **`app/api/users.py`** - Medium complexity
6. **`app/api/listings.py`** - Complex parallel queries
7. **`app/api/homes.py`** - Most complex with transactions
8. **`app/api/common.py`** - Generic service
9. **`app/main.py`** - Finalize lifespan management

### Testing Strategy:
- Migrate one file at a time
- Run full test suite after each migration
- Performance benchmark before/after

---

## Summary Table

| Aspect | asyncpg (Current) | SQLAlchemy Core |
|--------|-------------------|-----------------|
| Performance | Fastest | ~2-3x slower |
| Code Changes | None | ~500+ lines |
| Files Affected | 0 | 10+ files |
| Learning Curve | N/A | Medium |
| PostgreSQL-native | Yes | Abstracted |
| ORM-ready | No | Yes |
| Multi-DB support | No | Yes |
| Query Safety | Manual (our QueryBuilder) | Built-in |
| Recommendation | **Keep** | Switch only if needed |

---

## Files Quick Reference

| File | Change Level | Primary Changes |
|------|--------------|-----------------|
| `app/database/connection.py` | **MAJOR** | Pool → Engine, new imports |
| `app/database/query_builder.py` | **MODERATE** | `$n` → `:param` placeholders |
| `app/main.py` | **MODERATE** | Lifespan management |
| `app/api/users.py` | **SIGNIFICANT** | All query patterns |
| `app/api/homes.py` | **SIGNIFICANT** | Transactions, executemany |
| `app/api/listings.py` | **SIGNIFICANT** | Parallel queries, fetch patterns |
| `app/api/favorites.py` | **MODERATE** | Simple CRUD patterns |
| `app/api/common.py` | **SIGNIFICANT** | Generic listing service |
| `test/conftest.py` | **MODERATE** | Test fixtures |
| `migration/*.py` | **MINIMAL** | DDL execution |
