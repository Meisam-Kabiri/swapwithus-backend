from migration._001_create_users import create_users_table_sql
from migration._002_create_homes import create_homes_table_sql
from migration._003_create_images import create_images_table_sql
from migration._004_create_favorites import create_favorites_table_sql
from migration._005_create_books import create_books_table_sql
from migration._006_create_caravans import create_caravans_table_sql
from migration._007_create_clothes import create_clothes_table_sql




# @pytest.mark.asyncio # we can remove this cuz in the toml file we have set the marker globally to detect asyncs
async def test_create_homes_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_homes_table_sql())
        assert result == "CREATE INDEX"

async def test_create_users_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_users_table_sql())
        assert result == "CREATE TABLE"
        
async def test_create_images_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_images_table_sql())
        assert result == "CREATE INDEX"
        
async def test_create_favorites_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_favorites_table_sql())
        assert result == "CREATE INDEX"

async def test_create_books_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_books_table_sql())
        assert result == "CREATE INDEX"
        
        
# async def test_create_caravans_table(create_db_pool):
#     async with create_db_pool.acquire() as conn:
#         result = await conn.execute(create_caravans_table_sql())
#         assert result == "CREATE INDEX"
        
# async def test_create_clothes_table(create_db_pool):
#     async with create_db_pool.acquire() as conn:
#         result = await conn.execute(create_clothes_table_sql())
#         assert result == "CREATE INDEX"
        