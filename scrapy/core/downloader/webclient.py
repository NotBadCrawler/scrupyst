"""Deprecated HTTP/1.0 helper classes - no longer used with aiohttp"""

from __future__ import annotations

import warnings

from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.core.downloader.webclient module is deprecated and will be removed in a future Scrapy version."
    " The HTTP handlers now use aiohttp instead of Twisted.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

# Deprecated classes kept for backward compatibility but not functional
class ScrapyHTTPPageGetter:
    """Deprecated - no longer used"""

    def __init__(self):
        raise NotImplementedError(
            "ScrapyHTTPPageGetter is deprecated and no longer functional."
            " The HTTP handlers now use aiohttp."
        )


class ScrapyHTTPClientFactory:
    """Deprecated - no longer used"""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ScrapyHTTPClientFactory is deprecated and no longer functional."
            " The HTTP handlers now use aiohttp."
        )
