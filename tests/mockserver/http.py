"""HTTP mock server for tests.

This module now uses the aiohttp-based implementation.
The old Twisted-based implementation is kept in http_base.py and http_resources.py
for backward compatibility but is deprecated.
"""

from __future__ import annotations

# Re-export aiohttp-based MockServer as the default
from .http_aiohttp import MockServer, main

__all__ = ["MockServer", "main"]

