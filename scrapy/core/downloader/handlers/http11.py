"""Download handlers for http and https schemes"""

from __future__ import annotations

from scrapy.core.downloader.handlers.http11_aiohttp import (
    HTTP11DownloadHandler as AiohttpHTTP11DownloadHandler,
)


class HTTP11DownloadHandler(AiohttpHTTP11DownloadHandler):
    """HTTP/1.1 download handler using aiohttp (compatibility wrapper)"""

    pass


# For backward compatibility, export HTTPDownloadHandler as alias
HTTPDownloadHandler = HTTP11DownloadHandler


__all__ = [
    "HTTP11DownloadHandler",
    "HTTPDownloadHandler",
]
