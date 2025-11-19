from __future__ import annotations

import ssl
import warnings
from typing import TYPE_CHECKING, Any

from scrapy.core.downloader.tls import (
    DEFAULT_CIPHERS,
    TLS_METHOD_NAMES,
    get_ssl_context,
)
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import method_is_overridden
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


class ScrapyClientContextFactory:
    """
    Non-peer-certificate verifying HTTPS context factory for asyncio

    Default SSL method is ssl.PROTOCOL_TLS which allows TLS protocol negotiation
    """

    def __init__(
        self,
        method: str = "TLS",
        tls_verbose_logging: bool = False,
        tls_ciphers: str | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        self._ssl_method: str = method
        self.tls_verbose_logging: bool = tls_verbose_logging
        self.tls_ciphers: str = tls_ciphers or DEFAULT_CIPHERS
        if method_is_overridden(type(self), ScrapyClientContextFactory, "getContext"):
            warnings.warn(
                "Overriding ScrapyClientContextFactory.getContext() is deprecated and that method"
                " will be removed in a future Scrapy version. Override get_ssl_context() instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        method: str = "TLS",
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        tls_ciphers: str | None = crawler.settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]
        return cls(  # type: ignore[misc]
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            *args,
            **kwargs,
        )

    def get_ssl_context(self, hostname: str | None = None) -> ssl.SSLContext:
        """Get SSL context for the given hostname"""
        return get_ssl_context(
            method=self._ssl_method,
            verify_mode=ssl.CERT_NONE,  # Don't verify certificates by default
            ciphers=self.tls_ciphers,
            check_hostname=False,
        )

    # Legacy compatibility method
    def getContext(self, hostname: Any = None, port: Any = None) -> ssl.SSLContext:
        return self.get_ssl_context(
            hostname.decode("ascii") if isinstance(hostname, bytes) else hostname
        )


class BrowserLikeContextFactory(ScrapyClientContextFactory):
    """
    Recommended context factory for web clients using asyncio.

    Uses platform's root CAs for certificate verification.
    """

    def get_ssl_context(self, hostname: str | None = None) -> ssl.SSLContext:
        """Get SSL context that verifies certificates using platform trust store"""
        return get_ssl_context(
            method=self._ssl_method,
            verify_mode=ssl.CERT_REQUIRED,  # Verify certificates
            ciphers=self.tls_ciphers,
            check_hostname=True,
            load_default_certs=True,  # Use platform's root CAs
        )


class AcceptableProtocolsContextFactory:
    """Context factory to set up acceptable protocols for ALPN negotiation"""

    def __init__(self, context_factory: Any, acceptable_protocols: list[bytes]):
        self._wrapped_context_factory: Any = context_factory
        self._acceptable_protocols: list[bytes] = acceptable_protocols

    def get_ssl_context(self, hostname: str | None = None) -> ssl.SSLContext:
        """Get SSL context with ALPN protocols configured"""
        ctx = self._wrapped_context_factory.get_ssl_context(hostname)
        # Set ALPN protocols for protocol negotiation (e.g., HTTP/2)
        if self._acceptable_protocols:
            # Convert bytes to strings for ssl.SSLContext.set_alpn_protocols
            alpn_protocols = [p.decode("ascii") for p in self._acceptable_protocols]
            try:
                ctx.set_alpn_protocols(alpn_protocols)
            except (AttributeError, NotImplementedError):
                # ALPN not supported in this Python/OpenSSL version
                pass
        return ctx


def load_context_factory_from_settings(
    settings: BaseSettings, crawler: Crawler
) -> Any:
    ssl_method = TLS_METHOD_NAMES.get(
        settings.get("DOWNLOADER_CLIENT_TLS_METHOD"), "TLS"
    )
    context_factory_cls = load_object(settings["DOWNLOADER_CLIENTCONTEXTFACTORY"])
    # try method-aware context factory
    try:
        context_factory = build_from_crawler(
            context_factory_cls,
            crawler,
            method=ssl_method,
        )
    except TypeError:
        # use context factory defaults
        context_factory = build_from_crawler(
            context_factory_cls,
            crawler,
        )
        msg = (
            f"{settings['DOWNLOADER_CLIENTCONTEXTFACTORY']} does not accept "
            "a `method` argument (TLS method name, e.g. 'TLS' or 'TLSv1.2') "
            "and/or a `tls_verbose_logging` argument and/or a `tls_ciphers` "
            "argument. Please, upgrade your context factory class to handle "
            "them or ignore them."
        )
        warnings.warn(msg)

    return context_factory
