"""
FTP download handler - now using asyncio implementation.

For backward compatibility, this module exports the asyncio-based FTP handler.
"""

from __future__ import annotations

from scrapy.core.downloader.handlers.ftp_asyncio import FTPDownloadHandler

__all__ = ["FTPDownloadHandler"]
