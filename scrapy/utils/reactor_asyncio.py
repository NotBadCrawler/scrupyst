"""
Pure asyncio event loop management utilities.
This module replaces the Twisted reactor utilities with asyncio equivalents.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any, Callable, Generic, ParamSpec, TypeVar

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop


_T = TypeVar("_T")
_P = ParamSpec("_P")


def get_event_loop() -> AbstractEventLoop:
    """Get the current asyncio event loop.
    
    Creates a new event loop if one doesn't exist.
    
    Returns:
        The current event loop
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in current thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def set_event_loop_policy() -> None:
    """Set the appropriate event loop policy for the platform."""
    if sys.platform == "win32":
        policy = asyncio.get_event_loop_policy()
        if not isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class CallLaterOnce(Generic[_T]):
    """Schedule a function to be called in the next event loop iteration.
    
    Only schedules if it hasn't been already scheduled since the last time it ran.
    """

    def __init__(self, func: Callable[_P, _T], *a: _P.args, **kw: _P.kwargs):
        self._func: Callable[_P, _T] = func
        self._a: tuple[Any, ...] = a
        self._kw: dict[str, Any] = kw
        self._handle: asyncio.TimerHandle | None = None
        self._futures: list[asyncio.Future] = []

    def schedule(self, delay: float = 0) -> None:
        """Schedule the function to be called after delay seconds.
        
        Args:
            delay: Delay in seconds before calling the function
        """
        if self._handle is None:
            loop = get_event_loop()
            self._handle = loop.call_later(delay, self)

    def cancel(self) -> None:
        """Cancel a scheduled call."""
        if self._handle:
            self._handle.cancel()
            self._handle = None

    def __call__(self) -> _T:
        """Execute the scheduled function."""
        self._handle = None
        result = self._func(*self._a, **self._kw)

        loop = get_event_loop()
        for future in self._futures:
            loop.call_soon(future.set_result, None)
        self._futures = []

        return result

    async def wait(self) -> None:
        """Wait for the next execution of the scheduled function."""
        future: asyncio.Future = asyncio.Future()
        self._futures.append(future)
        await future


async def listen_tcp(
    portrange: list[int], host: str, protocol_factory: Callable[[], asyncio.Protocol]
) -> asyncio.Server:
    """Create a TCP server listening on a port from the range.
    
    Tries ports in the range until one succeeds.
    
    Args:
        portrange: List of 0, 1, or 2 elements specifying port range
        host: Host address to bind to
        protocol_factory: Factory function that creates protocol instances
        
    Returns:
        The created server
        
    Raises:
        ValueError: If portrange has more than 2 elements
        OSError: If no port in the range is available
    """
    loop = get_event_loop()
    
    if len(portrange) > 2:
        raise ValueError(f"invalid portrange: {portrange}")
    
    if not portrange:
        # Port 0 means let the OS choose
        return await loop.create_server(protocol_factory, host, 0)
    
    if len(portrange) == 1:
        return await loop.create_server(protocol_factory, host, portrange[0])
    
    # Try each port in the range
    last_error = None
    for port in range(portrange[0], portrange[1] + 1):
        try:
            return await loop.create_server(protocol_factory, host, port)
        except OSError as e:
            last_error = e
            if port == portrange[1]:
                raise
    
    # This shouldn't be reached, but satisfy type checker
    raise last_error  # type: ignore[misc]


def call_later(delay: float, func: Callable[_P, Any], *args: _P.args, **kwargs: _P.kwargs) -> asyncio.TimerHandle:
    """Call a function after a delay.
    
    Args:
        delay: Delay in seconds
        func: Function to call
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        A handle that can be used to cancel the call
    """
    loop = get_event_loop()
    
    def _wrapper():
        func(*args, **kwargs)
    
    return loop.call_later(delay, _wrapper)


def is_event_loop_installed() -> bool:
    """Check whether an event loop is running.
    
    Returns:
        True if an event loop is running, False otherwise
    """
    try:
        loop = asyncio.get_running_loop()
        return loop is not None
    except RuntimeError:
        return False
