
import pytest

from migration._001_create_users import create_users_table_sql
from migration._002_create_homes import create_homes_table_sql
from migration._003_create_images import create_images_table_sql
from migration._004_create_favorites import create_favorites_table_sql


# @pytest.mark.asyncio # we can remove this cuz in the toml file we have set the marker globally to detect asyncs
async def test_create_homes_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_homes_table_sql())
        assert result == "CREATE INDEX"
