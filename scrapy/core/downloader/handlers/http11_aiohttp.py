"""Download handlers for http and https schemes using aiohttp"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from io import BytesIO
from time import time
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import urldefrag

import aiohttp

from scrapy import Request, Spider, signals
from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.exceptions import StopDownload
from scrapy.http import Headers, Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from typing_extensions import NotRequired, Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class _ResultT(TypedDict):
    response: aiohttp.ClientResponse
    body: bytes
    flags: list[str] | None
    certificate: Any | None
    ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    failure: NotRequired[Exception | None]


class HTTP11DownloadHandler:
    """Aiohttp-based HTTP/1.1 download handler"""

    lazy = False

    def __init__(self, settings: BaseSettings, crawler: Crawler):
        self._crawler = crawler
        self._context_factory = load_context_factory_from_settings(settings, crawler)
        self._default_maxsize: int = settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize: int = settings.getint("DOWNLOAD_WARNSIZE")
        self._fail_on_dataloss: bool = settings.getbool("DOWNLOAD_FAIL_ON_DATALOSS")
        self._max_concurrent = settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN")
        
        # Create SSL context
        self._ssl_context = self._context_factory.get_ssl_context()
        
        # Create connector with connection pooling
        self._connector = aiohttp.TCPConnector(
            limit_per_host=self._max_concurrent,
            ssl=self._ssl_context,
            enable_cleanup_closed=True,
        )
        
        # Create session (will be created lazily when needed)
        self._session: aiohttp.ClientSession | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                connector_owner=False,  # We manage the connector
                timeout=aiohttp.ClientTimeout(total=None),  # We handle timeout separately
            )
        return self._session

    def download_request(self, request: Request, spider: Spider) -> asyncio.Future[Response]:
        """Download a request and return a Future of Response"""
        agent = ScrapyAiohttpAgent(
            session=self._get_session(),
            maxsize=getattr(spider, "download_maxsize", self._default_maxsize),
            warnsize=getattr(spider, "download_warnsize", self._default_warnsize),
            fail_on_dataloss=self._fail_on_dataloss,
            crawler=self._crawler,
        )
        # Ensure we return a Future, not a coroutine
        return asyncio.ensure_future(agent.download_request(request))

    async def close(self) -> None:
        """Close the handler and clean up resources"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector:
            await self._connector.close()


class ScrapyAiohttpAgent:
    """Agent that performs HTTP requests using aiohttp"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        maxsize: int = 0,
        warnsize: int = 0,
        fail_on_dataloss: bool = True,
        crawler: Crawler | None = None,
    ):
        self._session = session
        self._maxsize = maxsize
        self._warnsize = warnsize
        self._fail_on_dataloss = fail_on_dataloss
        self._crawler = crawler

    async def download_request(self, request: Request) -> Response:
        """Execute the HTTP request and return a Response object"""
        url = urldefrag(request.url)[0]
        method = request.method
        headers = dict(request.headers.to_unicode_dict())
        body = request.body if request.body else None
        timeout = request.meta.get("download_timeout", 180)
        
        # Handle proxy
        proxy = request.meta.get("proxy")
        proxy_auth = None
        if proxy:
            # Extract proxy authentication if present
            proxy_parsed = urlparse_cached(request)
            if proxy_parsed.username:
                proxy_auth = aiohttp.BasicAuth(
                    login=proxy_parsed.username,
                    password=proxy_parsed.password or "",
                )

        start_time = time()
        
        # Prepare timeout
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        
        try:
            # Execute request
            async with self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=body,
                proxy=proxy,
                proxy_auth=proxy_auth,
                timeout=timeout_obj,
                allow_redirects=False,  # Scrapy handles redirects
            ) as response:
                # Set download latency
                request.meta["download_latency"] = time() - start_time
                
                # Get response headers
                resp_headers = Headers(response.headers)
                
                # Send headers_received signal
                if self._crawler:
                    headers_received_result = self._crawler.signals.send_catch_log(
                        signal=signals.headers_received,
                        headers=resp_headers,
                        body_length=response.content_length or -1,
                        request=request,
                        spider=self._crawler.spider,
                    )
                    
                    # Check if any handler stopped the download
                    for handler, result in headers_received_result:
                        if isinstance(result, Exception) and isinstance(
                            result, StopDownload
                        ):
                            logger.debug(
                                "Download stopped for %(request)s from signal handler %(handler)s",
                                {"request": request, "handler": handler.__qualname__},
                            )
                            return self._build_response(
                                response,
                                b"",
                                url,
                                request,
                                flags=["download_stopped"],
                            )
                
                # Check maxsize before downloading
                maxsize = request.meta.get("download_maxsize", self._maxsize)
                warnsize = request.meta.get("download_warnsize", self._warnsize)
                expected_size = response.content_length or -1
                
                if maxsize and expected_size > maxsize:
                    warning_msg = (
                        f"Cancelling download of {url}: expected response "
                        f"size ({expected_size}) larger than download max size ({maxsize})."
                    )
                    logger.warning(warning_msg)
                    raise asyncio.CancelledError(warning_msg)
                
                if warnsize and expected_size > warnsize:
                    logger.warning(
                        "Expected response size (%(size)s) larger than "
                        "download warn size (%(warnsize)s) in request %(request)s.",
                        {"size": expected_size, "warnsize": warnsize, "request": request},
                    )
                
                # Read response body with size limits
                body_bytes = await self._read_body(
                    response, request, maxsize, warnsize
                )
                
                # Get connection info
                ip_address = None
                if response.connection:
                    try:
                        # Get peer address
                        peername = response.connection.transport.get_extra_info("peername")
                        if peername:
                            ip_address = ipaddress.ip_address(peername[0])
                    except (AttributeError, ValueError):
                        pass
                
                # Get SSL certificate info
                certificate = None
                try:
                    ssl_object = response.connection.transport.get_extra_info("ssl_object")
                    if ssl_object:
                        # Get peer certificate
                        cert_der = ssl_object.getpeercert(binary_form=True)
                        if cert_der:
                            import ssl
                            certificate = ssl.DER_cert_to_PEM_cert(cert_der)
                except (AttributeError, ValueError):
                    pass
                
                # Build and return response
                scrapy_response = self._build_response(
                    response, body_bytes, url, request, ip_address=ip_address
                )
                return scrapy_response
                
        except asyncio.TimeoutError:
            raise TimeoutError(f"Getting {url} took longer than {timeout} seconds.")
        except aiohttp.ClientError as e:
            logger.error(f"Error downloading {url}: {e}")
            raise

    async def _read_body(
        self,
        response: aiohttp.ClientResponse,
        request: Request,
        maxsize: int,
        warnsize: int,
    ) -> bytes:
        """Read response body with size limits and signal support"""
        bodybuf = BytesIO()
        bytes_received = 0
        reached_warnsize = False
        
        # Read in chunks
        async for chunk in response.content.iter_chunked(8192):
            bodybuf.write(chunk)
            bytes_received += len(chunk)
            
            # Send bytes_received signal
            if self._crawler:
                bytes_received_result = self._crawler.signals.send_catch_log(
                    signal=signals.bytes_received,
                    data=chunk,
                    request=request,
                    spider=self._crawler.spider,
                )
                
                # Check if any handler stopped the download
                for handler, result in bytes_received_result:
                    if isinstance(result, Exception) and isinstance(
                        result, StopDownload
                    ):
                        logger.debug(
                            "Download stopped for %(request)s from signal handler %(handler)s",
                            {"request": request, "handler": handler.__qualname__},
                        )
                        return bodybuf.getvalue()
            
            # Check maxsize
            if maxsize and bytes_received > maxsize:
                logger.warning(
                    "Received (%(bytes)s) bytes larger than download "
                    "max size (%(maxsize)s) in request %(request)s.",
                    {
                        "bytes": bytes_received,
                        "maxsize": maxsize,
                        "request": request,
                    },
                )
                bodybuf.truncate(0)
                raise asyncio.CancelledError("Response too large")
            
            # Check warnsize
            if warnsize and bytes_received > warnsize and not reached_warnsize:
                reached_warnsize = True
                logger.warning(
                    "Received more bytes than download "
                    "warn size (%(warnsize)s) in request %(request)s.",
                    {"warnsize": warnsize, "request": request},
                )
        
        return bodybuf.getvalue()

    def _build_response(
        self,
        aio_response: aiohttp.ClientResponse,
        body: bytes,
        url: str,
        request: Request,
        flags: list[str] | None = None,
        ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None,
        certificate: Any | None = None,
    ) -> Response:
        """Build a Scrapy Response from aiohttp response"""
        headers = Headers(aio_response.headers)
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
        
        # Get HTTP version
        protocol = f"HTTP/{aio_response.version.major}.{aio_response.version.minor}"
        
        return respcls(
            url=url,
            status=aio_response.status,
            headers=headers,
            body=body,
            flags=flags,
            certificate=certificate,
            ip_address=ip_address,
            protocol=protocol,
            request=request,
        )
