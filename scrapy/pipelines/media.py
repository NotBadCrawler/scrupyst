from __future__ import annotations

import asyncio
import functools
import logging
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.request import NO_CALLBACK, Request
from scrapy.utils.asyncio import call_later
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _DEFER_DELAY,
    _defer_sleep,
    Failure,
    deferred_from_coro,
    ensure_awaitable,
)
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import Settings
    from scrapy.utils.request import RequestFingerprinterProtocol


class FileInfo(TypedDict):
    url: str
    path: str
    checksum: str | None
    status: str


FileInfoOrError: TypeAlias = (
    tuple[Literal[True], FileInfo] | tuple[Literal[False], Failure]
)

logger = logging.getLogger(__name__)


class MediaPipeline(ABC):
    LOG_FAILED_RESULTS: bool = True

    class SpiderInfo:
        def __init__(self, spider: Spider):
            self.spider: Spider = spider
            self.downloading: set[bytes] = set()
            self.downloaded: dict[bytes, FileInfo | Failure] = {}
            self.waiting: defaultdict[bytes, list[asyncio.Future[FileInfo]]] = (
                defaultdict(list)
            )

    def __init__(
        self,
        download_func: Callable[[Request, Spider], Response] | None = None,
        *,
        crawler: Crawler,
    ):
        self.crawler: Crawler = crawler
        assert crawler.request_fingerprinter
        self._fingerprinter: RequestFingerprinterProtocol = (
            crawler.request_fingerprinter
        )
        self.download_func = download_func

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe, base_class_name="MediaPipeline", settings=settings
        )
        self.allow_redirects: bool = settings.getbool(
            resolve("MEDIA_ALLOW_REDIRECTS"), False
        )
        self._handle_statuses(self.allow_redirects)

    def _handle_statuses(self, allow_redirects: bool) -> None:
        self.handle_httpstatus_list = None
        if allow_redirects:
            self.handle_httpstatus_list = SequenceExclude(range(300, 400))

    def _key_for_pipe(
        self,
        key: str,
        base_class_name: str | None = None,
        settings: Settings | None = None,
    ) -> str:
        class_name = self.__class__.__name__
        formatted_key = f"{class_name.upper()}_{key}"
        if (
            not base_class_name
            or class_name == base_class_name
            or (settings and not settings.get(formatted_key))
        ):
            return key
        return formatted_key

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler=crawler)

    @_warn_spider_arg
    def open_spider(self, spider: Spider | None = None) -> None:
        assert self.crawler.spider
        self.spiderinfo = self.SpiderInfo(self.crawler.spider)

    @_warn_spider_arg
    def process_item(
        self, item: Any, spider: Spider | None = None
    ) -> asyncio.Future[Any]:
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        tasks = [self._process_request(r, info, item) for r in requests]
        
        async def _gather_and_complete() -> Any:
            results: list[FileInfoOrError] = []
            for task in tasks:
                try:
                    result = await task
                    results.append((True, result))
                except Exception as e:
                    results.append((False, Failure(e)))
            return self.item_completed(results, item, info)
        
        return asyncio.ensure_future(_gather_and_complete())

    async def _process_request(
        self, request: Request, info: SpiderInfo, item: Any
    ) -> FileInfo:
        fp = self._fingerprinter.fingerprint(request)

        eb = request.errback
        request.callback = NO_CALLBACK
        request.errback = None

        # Return cached result if request was already seen
        if fp in info.downloaded:
            await _defer_sleep()
            cached_result = info.downloaded[fp]
            if isinstance(cached_result, Failure):
                if eb:
                    return eb(cached_result)
                cached_result.raiseException()
            return cached_result

        # Otherwise, wait for result
        wad: asyncio.Future[FileInfo] = asyncio.Future()
        if eb:
            # Add errback via callback that checks for exception
            def _handle_done(future: asyncio.Future[FileInfo]) -> None:
                if future.exception():
                    eb(Failure(future.exception()))
            wad.add_done_callback(_handle_done)
        info.waiting[fp].append(wad)

        # Check if request is downloading right now to avoid doing it twice
        if fp in info.downloading:
            return await wad

        # Download request checking media_to_download hook output first
        info.downloading.add(fp)
        await _defer_sleep()
        result: FileInfo | Failure
        try:
            file_info = await ensure_awaitable(
                self.media_to_download(request, info, item=item)
            )
            if file_info:
                # got a result without downloading
                result = file_info
            else:
                # download the result
                result = await self._check_media_to_download(request, info, item=item)
        except Exception as e:
            result = Failure(e)
            logger.exception(result)
        self._cache_result_and_execute_waiters(result, fp, info)
        return await wad  # it must return wad at last

    def _modify_media_request(self, request: Request) -> None:
        if self.handle_httpstatus_list:
            request.meta["handle_httpstatus_list"] = self.handle_httpstatus_list
        else:
            request.meta["handle_httpstatus_all"] = True

    async def _check_media_to_download(
        self, request: Request, info: SpiderInfo, item: Any
    ) -> FileInfo:
        try:
            if self.download_func:
                # this ugly code was left only to support tests. TODO: remove
                response = await ensure_awaitable(self.download_func(request, info.spider))
            else:
                self._modify_media_request(request)
                assert self.crawler.engine
                response = await deferred_from_coro(
                    self.crawler.engine.download_async(request)
                )
            return self.media_downloaded(response, request, info, item=item)
        except Exception:
            failure = self.media_failed(Failure(), request, info)
            if isinstance(failure, Failure):
                warnings.warn(
                    f"{global_object_name(self.media_failed)} returned a Failure instance."
                    f" This is deprecated, please raise an exception instead, e.g. via failure.raiseException().",
                    category=ScrapyDeprecationWarning,
                    stacklevel=2,
                )
                failure.raiseException()

    def _cache_result_and_execute_waiters(
        self, result: FileInfo | Failure, fp: bytes, info: SpiderInfo
    ) -> None:
        if isinstance(result, Failure):
            # minimize cached information for failure
            result.cleanFailure()
            result.frames = []
            # This code fixes a memory leak by avoiding to keep references to
            # the Request and Response objects on the Media Pipeline cache.
            #
            # What happens when the media_downloaded callback raises an
            # exception, for example a FileException('download-error') when
            # the Response status code is not 200 OK, is that the original
            # StopIteration exception (which in turn contains the failed
            # Response and by extension, the original Request) gets encapsulated
            # within the FileException context.
            #
            # Originally, Scrapy was using twisted.internet.defer.returnValue
            # inside functions decorated with twisted.internet.defer.inlineCallbacks,
            # encapsulating the returned Response in a _DefGen_Return exception
            # instead of a StopIteration.
            #
            # To avoid keeping references to the Response and therefore Request
            # objects on the Media Pipeline cache, we should wipe the context of
            # the encapsulated exception when it is a StopIteration instance
            context = getattr(result.value, "__context__", None)
            if isinstance(context, StopIteration):
                result.value.__context__ = None

        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            if isinstance(result, Failure):
                call_later(_DEFER_DELAY, wad.set_exception, result.value)
            else:
                call_later(_DEFER_DELAY, wad.set_result, result)

    # Overridable Interface
    @abstractmethod
    def media_to_download(
        self, request: Request, info: SpiderInfo, *, item: Any = None
    ) -> asyncio.Future[FileInfo | None] | FileInfo | None:
        """Check request before starting download"""
        raise NotImplementedError

    @abstractmethod
    def get_media_requests(self, item: Any, info: SpiderInfo) -> list[Request]:
        """Returns the media requests to download"""
        raise NotImplementedError

    @abstractmethod
    def media_downloaded(
        self,
        response: Response,
        request: Request,
        info: SpiderInfo,
        *,
        item: Any = None,
    ) -> FileInfo:
        """Handler for success downloads"""
        raise NotImplementedError

    @abstractmethod
    def media_failed(
        self, failure: Failure, request: Request, info: SpiderInfo
    ) -> Failure:
        """Handler for failed downloads"""
        raise NotImplementedError

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: SpiderInfo
    ) -> Any:
        """Called per item when all media requests has been processed"""
        if self.LOG_FAILED_RESULTS:
            for ok, value in results:
                if not ok:
                    assert isinstance(value, Failure)
                    logger.error(
                        "%(class)s found errors processing %(item)s",
                        {"class": self.__class__.__name__, "item": item},
                        exc_info=failure_to_exc_info(value),
                        extra={"spider": info.spider},
                    )
        return item

    @abstractmethod
    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        """Returns the path where downloaded media should be stored"""
        raise NotImplementedError
