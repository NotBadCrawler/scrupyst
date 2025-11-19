"""HTTP/2 download handler using aiohttp"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.core.downloader.handlers.http11_aiohttp import HTTP11DownloadHandler

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import Settings


class H2DownloadHandler(HTTP11DownloadHandler):
    """
    HTTP/2 download handler using aiohttp.
    
    Note: aiohttp automatically negotiates HTTP/2 via ALPN when available.
    This handler uses the same implementation as HTTP/1.1 since aiohttp
    handles protocol negotiation automatically.
    """

    def __init__(self, settings: Settings, crawler: Crawler):
        super().__init__(settings, crawler)
        
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)
