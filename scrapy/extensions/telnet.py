"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst

NOTE: This module is currently non-functional in the asyncio migration.
The Twisted Conch dependency has been removed. A future implementation
may use asyncio-telnet or similar library, or this feature may be deprecated.
"""

from __future__ import annotations

import binascii
import logging
import os
import warnings
from typing import TYPE_CHECKING

from scrapy import signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)

# signal to update telnet variables
# args: telnet_vars
update_telnet_vars = object()


class TelnetConsole:
    """Telnet Console extension (currently non-functional after asyncio migration).
    
    This extension relied on twisted.conch which has been removed in the asyncio
    migration. Consider using alternative debugging methods:
    - scrapy shell
    - Python debugger (pdb)
    - Remote debugging tools
    """

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("TELNETCONSOLE_ENABLED"):
            raise NotConfigured
        
        warnings.warn(
            "TelnetConsole extension is currently non-functional after Twisted removal. "
            "Please use 'scrapy shell' or Python's debugger (pdb) for interactive debugging. "
            "This extension may be re-implemented using asyncio-telnet in the future or deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        
        self.crawler: Crawler = crawler
        self.portrange: list[int] = [
            int(x) for x in crawler.settings.getlist("TELNETCONSOLE_PORT")
        ]
        self.host: str = crawler.settings["TELNETCONSOLE_HOST"]
        self.username: str = crawler.settings["TELNETCONSOLE_USERNAME"]
        self.password: str = crawler.settings["TELNETCONSOLE_PASSWORD"]

        if not self.password:
            self.password = binascii.hexlify(os.urandom(8)).decode("utf8")
            logger.warning(
                "Telnet console is disabled (non-functional after asyncio migration). "
                "Generated password was: %s (not used)",
                self.password
            )

        # Don't connect signals - the extension doesn't work anyway
        # self.crawler.signals.connect(self.start_listening, signals.engine_started)
        # self.crawler.signals.connect(self.stop_listening, signals.engine_stopped)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def start_listening(self) -> None:
        """Placeholder - telnet console is non-functional."""
        logger.warning(
            "Telnet console cannot start - feature is non-functional after asyncio migration"
        )

    def stop_listening(self) -> None:
        """Placeholder - telnet console is non-functional."""
        pass
