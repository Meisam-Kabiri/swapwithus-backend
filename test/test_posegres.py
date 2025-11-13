from migration._002_create_homes import create_homes_table_sql


# @pytest.mark.asyncio # we can remove this cuz in the toml file we have set the marker globally to detect asyncs
async def test_create_homes_table(create_db_pool):
    async with create_db_pool.acquire() as conn:
        result = await conn.execute(create_homes_table_sql())
        assert result == "CREATE INDEX"
