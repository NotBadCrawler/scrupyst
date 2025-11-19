from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Any

from scrapy.utils.datatypes import LocalCache

if TYPE_CHECKING:
    from collections.abc import Sequence

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler

# TODO: cache misses
dnscache: LocalCache[str, Any] = LocalCache(10000)


class CachingThreadedResolver:
    """
    Default caching resolver. IPv4 only, supports setting a timeout value for DNS requests.
    
    This is an asyncio-based implementation that replaces Twisted's ThreadedResolver.
    """

    def __init__(self, cache_size: int, timeout: float):
        dnscache.limit = cache_size
        self.timeout = timeout

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(cache_size, crawler.settings.getfloat("DNS_TIMEOUT"))

    def install_on_reactor(self) -> None:
        """No-op for compatibility. Asyncio doesn't require reactor installation."""
        pass

    async def getHostByName(self, name: str, timeout: Sequence[int] | None = None) -> str:
        """
        Resolve a hostname to an IPv4 address.
        
        Args:
            name: The hostname to resolve
            timeout: Timeout values (ignored, self.timeout is used instead)
            
        Returns:
            The resolved IP address as a string
        """
        if name in dnscache:
            return dnscache[name]
        
        # Use asyncio's getaddrinfo for DNS resolution
        try:
            loop = asyncio.get_event_loop()
            # AF_INET for IPv4 only, SOCK_STREAM for TCP
            addrinfo = await asyncio.wait_for(
                loop.getaddrinfo(name, None, family=socket.AF_INET, type=socket.SOCK_STREAM),
                timeout=self.timeout
            )
            if not addrinfo:
                raise socket.gaierror(f"No address found for {name}")
            
            # Extract the IP address from the first result
            # addrinfo format: [(family, type, proto, canonname, sockaddr), ...]
            # sockaddr format: (address, port)
            result = addrinfo[0][4][0]
            
            if dnscache.limit:
                dnscache[name] = result
            
            return result
        except asyncio.TimeoutError as e:
            raise socket.timeout(f"DNS lookup timed out for {name}") from e


class CachingHostnameResolver:
    """
    Experimental caching resolver. Resolves IPv4 and IPv6 addresses.
    
    This is an asyncio-based implementation that replaces Twisted's hostname resolver.
    """

    def __init__(self, cache_size: int):
        dnscache.limit = cache_size

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(cache_size)

    def install_on_reactor(self) -> None:
        """No-op for compatibility. Asyncio doesn't require reactor installation."""
        pass

    async def resolveHostName(
        self,
        hostName: str,
        portNumber: int = 0,
        addressTypes: Sequence[int] | None = None,
        transportSemantics: str = "TCP",
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        """
        Resolve a hostname to a list of addresses (IPv4 and/or IPv6).
        
        Args:
            hostName: The hostname to resolve
            portNumber: Port number (optional)
            addressTypes: Address family types to resolve (optional)
            transportSemantics: Transport type (TCP/UDP)
            
        Returns:
            List of address info tuples
        """
        try:
            addresses = dnscache[hostName]
            return addresses
        except KeyError:
            pass
        
        # Use asyncio's getaddrinfo for DNS resolution
        loop = asyncio.get_event_loop()
        
        # Determine socket type from transport semantics
        sock_type = socket.SOCK_STREAM if transportSemantics == "TCP" else socket.SOCK_DGRAM
        
        # If addressTypes not specified, resolve both IPv4 and IPv6
        family = socket.AF_UNSPEC
        if addressTypes:
            # Map address types if provided (simplified mapping)
            family = addressTypes[0] if addressTypes else socket.AF_UNSPEC
        
        addrinfo = await loop.getaddrinfo(
            hostName, portNumber, family=family, type=sock_type
        )
        
        if dnscache.limit and addrinfo:
            dnscache[hostName] = addrinfo
        
        return addrinfo
