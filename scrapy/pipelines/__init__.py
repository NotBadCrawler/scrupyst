"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from __future__ import annotations

import asyncio
import warnings
from typing import TYPE_CHECKING, Any, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    deferred_from_coro,
    ensure_awaitable,
    maybeDeferred_coro,
)
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from scrapy.utils.defer import Failure

    from scrapy import Spider
    from scrapy.settings import Settings


class ItemPipelineManager(MiddlewareManager):
    component_name = "item pipeline"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list[Any]:
        return build_component_list(settings.getwithbase("ITEM_PIPELINES"))

    def _add_middleware(self, pipe: Any) -> None:
        if hasattr(pipe, "open_spider"):
            self.methods["open_spider"].append(pipe.open_spider)
            self._check_mw_method_spider_arg(pipe.open_spider)
        if hasattr(pipe, "close_spider"):
            self.methods["close_spider"].appendleft(pipe.close_spider)
            self._check_mw_method_spider_arg(pipe.close_spider)
        if hasattr(pipe, "process_item"):
            self.methods["process_item"].append(pipe.process_item)
            self._check_mw_method_spider_arg(pipe.process_item)

    def process_item(self, item: Any, spider: Spider) -> asyncio.Future[Any]:
        warnings.warn(
            f"{global_object_name(type(self))}.process_item() is deprecated, use process_item_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return deferred_from_coro(self.process_item_async(item))

    async def process_item_async(self, item: Any) -> Any:
        return await self._process_chain("process_item", item, add_spider=True)

    def _process_parallel(self, methodname: str) -> asyncio.Future[list[None]]:
        methods = cast("Iterable[Callable[..., None]]", self.methods[methodname])

        async def gather_methods() -> list[None]:
            tasks = []
            for method in methods:
                if method in self._mw_methods_requiring_spider:
                    task = ensure_awaitable(maybeDeferred_coro(method, self._spider))
                else:
                    task = ensure_awaitable(maybeDeferred_coro(method))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for exceptions and re-raise the first one
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            
            return list(results)  # type: ignore[return-value]
        
        return asyncio.ensure_future(gather_methods())

    def open_spider(self, spider: Spider) -> asyncio.Future[list[None]]:
        warnings.warn(
            f"{global_object_name(type(self))}.open_spider() is deprecated, use open_spider_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return self._process_parallel("open_spider")

    async def open_spider_async(self) -> None:
        await self._process_parallel("open_spider")

    def close_spider(self, spider: Spider) -> asyncio.Future[list[None]]:
        warnings.warn(
            f"{global_object_name(type(self))}.close_spider() is deprecated, use close_spider_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return self._process_parallel("close_spider")

    async def close_spider_async(self) -> None:
        await self._process_parallel("close_spider")
