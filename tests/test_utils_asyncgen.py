from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
# Removed deferred_f_from_coro_f import


class TestAsyncgenUtils:
    @pytest.mark.asyncio
    async def test_as_async_generator(self):
        ag = as_async_generator(range(42))
        results = [i async for i in ag]
        assert results == list(range(42))

    @pytest.mark.asyncio
    async def test_collect_asyncgen(self):
        ag = as_async_generator(range(42))
        results = await collect_asyncgen(ag)
        assert results == list(range(42))
