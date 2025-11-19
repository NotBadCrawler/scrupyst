"""Download handlers for http and https schemes"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from scrapy.core.downloader.handlers.http11_aiohttp import HTTP11DownloadHandler
from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


class HTTP10DownloadHandler(HTTP11DownloadHandler):
    """Deprecated HTTP/1.0 handler - now uses HTTP/1.1 implementation"""
    
    lazy = False

    def __init__(self, settings: BaseSettings, crawler: Crawler):
        warnings.warn(
            "HTTP10DownloadHandler is deprecated and will be removed in a future Scrapy version."
            " It now uses the HTTP/1.1 implementation.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        super().__init__(settings, crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)
