"""
DEPRECATED: Old Twisted-based HTTP/2 implementation.

This module has been deprecated and replaced with aiohttp-based HTTP/2 support.
See scrapy.core.downloader.handlers.http2_aiohttp for the new implementation.

This module is kept for backward compatibility with tests only and will be 
removed in a future version.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "scrapy.core.http2 module is deprecated. "
    "HTTP/2 support is now provided through aiohttp. "
    "Use scrapy.core.downloader.handlers.http2_aiohttp instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = []
