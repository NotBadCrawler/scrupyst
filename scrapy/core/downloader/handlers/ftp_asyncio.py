"""
FTP download handler using asyncio's aioftp library.

Note: This is a basic implementation. For production use, you may need to install aioftp:
    pip install aioftp

If aioftp is not installed, FTP downloads will not be supported.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    import asyncio

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class FTPDownloadHandler:
    """
    Asyncio-based FTP download handler.
    
    Currently marks FTP as not supported. To enable FTP support:
    1. Install aioftp: pip install aioftp
    2. Implement async FTP client functionality
    """

    lazy = False

    CODE_MAPPING: dict[str, int] = {
        "550": 404,
        "default": 503,
    }

    def __init__(self, settings: BaseSettings):
        self.default_user = settings["FTP_USER"]
        self.default_password = settings["FTP_PASSWORD"]
        self.passive_mode = settings["FTP_PASSIVE_MODE"]
        
        # Check if aioftp is available
        try:
            import aioftp  # noqa: F401
            self._aioftp_available = True
        except ImportError:
            logger.warning(
                "FTP support requires the aioftp library. "
                "Install it with: pip install aioftp"
            )
            self._aioftp_available = False
            raise NotConfigured("FTP handler requires aioftp library")

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def download_request(self, request: Request, spider: Spider) -> asyncio.Future[Response]:
        """Download a file via FTP"""
        import asyncio
        
        if not self._aioftp_available:
            future: asyncio.Future[Response] = asyncio.Future()
            future.set_exception(
                NotConfigured("FTP handler requires aioftp library")
            )
            return future
        
        return asyncio.ensure_future(self._download_ftp(request))

    async def _download_ftp(self, request: Request) -> Response:
        """
        Async FTP download implementation.
        
        This is a placeholder that would need aioftp implementation.
        """
        import aioftp
        
        parsed_url = urlparse_cached(request)
        user = request.meta.get("ftp_user", self.default_user)
        password = request.meta.get("ftp_password", self.default_password)
        filepath = unquote(parsed_url.path)
        host = parsed_url.hostname
        port = parsed_url.port or 21
        
        # Connect to FTP server
        async with aioftp.Client.context(host, port, user, password) as client:
            # Download file
            local_filename = request.meta.get("ftp_local_filename")
            
            if local_filename:
                # Download to local file
                await client.download(filepath, local_filename)
                body = to_bytes(local_filename)
                size = 0  # Could get actual file size here
            else:
                # Download to memory
                from io import BytesIO
                buffer = BytesIO()
                await client.download(filepath, buffer, write_into=True)
                body = buffer.getvalue()
                size = len(body)
            
            # Build response
            headers = {
                "local filename": local_filename or b"",
                "size": size,
            }
            respcls = responsetypes.from_args(url=request.url, body=body)
            return respcls(
                url=request.url,
                status=200,
                body=body,
                headers=headers,  # type: ignore[arg-type]
            )
