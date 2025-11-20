"""
Pure asyncio event loop management utilities.
Replaces Twisted reactor utilities with asyncio equivalents.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any, Generic, ParamSpec, TypeVar
from warnings import catch_warnings, filterwarnings

from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable


_T = TypeVar("_T")
_P = ParamSpec("_P")

# Constant for asyncio reactor path (for backward compatibility)
_asyncio_reactor_path = "asyncio"


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
    loop = asyncio.get_event_loop()

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
            loop = asyncio.get_event_loop()
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

        loop = asyncio.get_event_loop()
        for future in self._futures:
            loop.call_soon(future.set_result, None)
        self._futures = []

        return result

    async def wait(self) -> None:
        """Wait for the next execution of the scheduled function."""
        future: asyncio.Future = asyncio.Future()
        self._futures.append(future)
        await future


def set_asyncio_event_loop_policy() -> None:
    """Set the appropriate event loop policy for the platform.

    On Windows, use WindowsSelectorEventLoopPolicy for compatibility.
    """
    if sys.platform == "win32":
        policy = asyncio.get_event_loop_policy()
        if not isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def install_reactor(reactor_path: str, event_loop_path: str | None = None) -> None:
    """Install the asyncio event loop.

    In pure asyncio mode, this primarily sets up the event loop policy and
    optionally installs a custom event loop.

    Args:
        reactor_path: Ignored in pure asyncio mode (kept for API compatibility)
        event_loop_path: Optional path to a custom event loop class
    """
    set_asyncio_event_loop_policy()
    set_asyncio_event_loop(event_loop_path)


def _get_asyncio_event_loop() -> AbstractEventLoop:
    """Get or create the asyncio event loop."""
    return set_asyncio_event_loop(None)


def set_asyncio_event_loop(event_loop_path: str | None) -> AbstractEventLoop:
    """Set and return the event loop with specified import path.

    Args:
        event_loop_path: Optional path to a custom event loop class

    Returns:
        The event loop instance
    """
    if event_loop_path is not None:
        event_loop_class: type[AbstractEventLoop] = load_object(event_loop_path)
        event_loop = _get_asyncio_event_loop()
        if not isinstance(event_loop, event_loop_class):
            event_loop = event_loop_class()
            asyncio.set_event_loop(event_loop)
    else:
        try:
            with catch_warnings():
                # In Python 3.10.9, 3.11.1, 3.12 and 3.13, a DeprecationWarning
                # is emitted about the lack of a current event loop, because in
                # Python 3.14 and later `get_event_loop` will raise a
                # RuntimeError in that event. Because our code is already
                # prepared for that future behavior, we ignore the deprecation
                # warning.
                filterwarnings(
                    "ignore",
                    message="There is no current event loop",
                    category=DeprecationWarning,
                )
                event_loop = asyncio.get_event_loop()
        except RuntimeError:
            # `get_event_loop` raises RuntimeError when called with no asyncio
            # event loop yet installed in the following scenarios:
            # - Previsibly on Python 3.14 and later.
            #   https://github.com/python/cpython/issues/100160#issuecomment-1345581902
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
    return event_loop


def verify_installed_reactor(reactor_path: str) -> None:
    """Verify that the asyncio event loop is installed.

    In pure asyncio mode, this always passes. Kept for API compatibility.

    Args:
        reactor_path: Ignored in pure asyncio mode
    """
    # In pure asyncio mode, we don't need to verify reactor installation


def verify_installed_asyncio_event_loop(loop_path: str) -> None:
    """Verify that the installed event loop matches the specified import path.

    Args:
        loop_path: Path to the expected event loop class

    Raises:
        RuntimeError: If the event loop doesn't match the expected class
    """
    if not is_event_loop_running():
        # If no loop is running, check the current event loop
        try:
            event_loop = asyncio.get_event_loop()
        except RuntimeError:
            raise RuntimeError(
                "verify_installed_asyncio_event_loop() called without an event loop."
            )
    else:
        event_loop = asyncio.get_running_loop()

    loop_class = load_object(loop_path)
    if isinstance(event_loop, loop_class):
        return

    installed = (
        f"{event_loop.__class__.__module__}"
        f".{event_loop.__class__.__qualname__}"
    )
    raise RuntimeError(
        f"The installed event loop class ({installed}) does "
        f"not match the one specified ({loop_path})"
    )


def is_reactor_installed() -> bool:
    """Check whether an event loop exists.

    In pure asyncio mode, this checks if an event loop is available.
    Kept for API compatibility with Twisted-based code.

    Returns:
        True if an event loop exists, False otherwise
    """
    try:
        asyncio.get_event_loop()
        return True
    except RuntimeError:
        return False


def is_asyncio_reactor_installed() -> bool:
    """Check whether asyncio is available.

    In pure asyncio mode, this always returns True if an event loop exists.
    Kept for API compatibility.

    Returns:
        True if an event loop exists, False otherwise
    """
    return is_reactor_installed()


def is_event_loop_running() -> bool:
    """Check whether an event loop is currently running.

    Returns:
        True if an event loop is running, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False
