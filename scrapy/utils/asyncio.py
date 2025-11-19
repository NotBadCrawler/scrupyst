"""Utilities related to asyncio support in Scrapy."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

from scrapy.utils.asyncgen import as_async_generator

if TYPE_CHECKING:
    # typing.Self, typing.TypeVarTuple and typing.Unpack require Python 3.11
    from typing_extensions import Self, TypeVarTuple, Unpack

    _Ts = TypeVarTuple("_Ts")


_T = TypeVar("_T")
_P = ParamSpec("_P")


logger = logging.getLogger(__name__)


def is_asyncio_available() -> bool:
    """Check if it's possible to call asyncio code that relies on the asyncio event loop.

    .. versionadded:: VERSION

    This function returns ``True`` if an asyncio event loop is available.
    When this returns ``True``, an asyncio loop is installed and used by
    Scrapy. It's possible to call functions that require it, such as
    :func:`asyncio.sleep`, and await on :class:`asyncio.Future` objects in
    Scrapy-related code.

    Returns:
        True if asyncio is available, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        # No running event loop
        try:
            asyncio.get_event_loop()
            return True
        except RuntimeError:
            return False


async def _parallel_asyncio(
    iterable: Iterable[_T] | AsyncIterator[_T],
    count: int,
    callable_: Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> None:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    This function is only used in
    :meth:`scrapy.core.scraper.Scraper.handle_spider_output_async` and so it
    assumes that neither *callable* nor iterating *iterable* will raise an
    exception.
    """
    queue: asyncio.Queue[_T | None] = asyncio.Queue()

    async def worker() -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                await callable_(item, *args, **kwargs)
            finally:
                queue.task_done()

    async def fill_queue() -> None:
        async for item in as_async_generator(iterable):
            await queue.put(item)
        for _ in range(count):
            await queue.put(None)

    fill_task = asyncio.create_task(fill_queue())
    work_tasks = [asyncio.create_task(worker()) for _ in range(count)]
    await asyncio.wait([fill_task, *work_tasks])


class AsyncioLoopingCall:
    """A simple implementation of a periodic call using asyncio, keeping
    some API and behavior compatibility with the Twisted ``LoopingCall``.

    The function is called every *interval* seconds, independent of the finish
    time of the previous call. If the function  is still running when it's time
    to call it again, calls are skipped until the function finishes.

    The function must not return a coroutine or a ``Deferred``.
    """

    def __init__(self, func: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs):
        self._func: Callable[_P, _T] = func
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self._task: asyncio.Task | None = None
        self.interval: float | None = None
        self._start_time: float | None = None

    @property
    def running(self) -> bool:
        return self._start_time is not None

    def start(self, interval: float, now: bool = True) -> None:
        """Start calling the function every *interval* seconds.

        :param interval: The interval in seconds between calls.
        :type interval: float

        :param now: If ``True``, also call the function immediately.
        :type now: bool
        """
        if self.running:
            raise RuntimeError("AsyncioLoopingCall already running")

        if interval <= 0:
            raise ValueError("Interval must be greater than 0")

        self.interval = interval
        self._start_time = time.time()
        if now:
            self._call()
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._loop())

    def _to_sleep(self) -> float:
        """Return the time to sleep until the next call."""
        assert self.interval is not None
        assert self._start_time is not None
        now = time.time()
        running_for = now - self._start_time
        return self.interval - (running_for % self.interval)

    async def _loop(self) -> None:
        """Run an infinite loop that calls the function periodically."""
        while self.running:
            await asyncio.sleep(self._to_sleep())
            self._call()

    def stop(self) -> None:
        """Stop the periodic calls."""
        self.interval = self._start_time = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _call(self) -> None:
        """Execute the function."""
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception:
            logger.exception("Error calling the AsyncioLoopingCall function")
            self.stop()
        else:
            if isinstance(result, Coroutine):
                self.stop()
                raise TypeError(
                    "The AsyncioLoopingCall function must not return a coroutine"
                )


def create_looping_call(
    func: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs
) -> AsyncioLoopingCall:
    """Create an instance of a looping call class.

    This creates an instance of :class:`AsyncioLoopingCall` for periodic function calls.
    """
    return AsyncioLoopingCall(func, *args, **kwargs)


def call_later(
    delay: float, func: Callable[[Unpack[_Ts]], object], *args: Unpack[_Ts]
) -> CallLaterResult:
    """Schedule a function to be called after a delay.

    This uses ``loop.call_later()`` from asyncio.
    """
    loop = asyncio.get_event_loop()
    return CallLaterResult.from_asyncio(loop.call_later(delay, func, *args))


class CallLaterResult:
    """A wrapper for :func:`call_later`, wrapping :class:`asyncio.TimerHandle`.

    The provided API is close to the :class:`asyncio.TimerHandle` one: there is
    no ``active()`` (as there is no such public API in
    :class:`asyncio.TimerHandle`) but ``cancel()`` can be called on already
    called or cancelled instances.
    """

    _timer_handle: asyncio.TimerHandle | None = None

    @classmethod
    def from_asyncio(cls, timer_handle: asyncio.TimerHandle) -> Self:
        """Create a CallLaterResult from an asyncio TimerHandle."""
        o = cls()
        o._timer_handle = timer_handle
        return o

    def cancel(self) -> None:
        """Cancel the underlying delayed call.

        Does nothing if the delayed call was already called or cancelled.
        """
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
