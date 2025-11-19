"""
Helper functions for dealing with asyncio tasks and futures.
Replaces Twisted deferred utilities with pure asyncio equivalents.
"""

from __future__ import annotations

import asyncio
import inspect
from asyncio import Future
from collections.abc import Awaitable, Coroutine, Iterable
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable


_T = TypeVar("_T")
_T2 = TypeVar("_T2")
_P = ParamSpec("_P")


_DEFER_DELAY = 0.1


class Failure:
    """A simple wrapper for exceptions, replacing twisted.python.failure.Failure.
    
    This class provides a compatible interface for error handling in asyncio,
    wrapping exceptions with .value and .check() methods.
    """
    
    def __init__(self, exc_value: BaseException | None = None, exc_type: type[BaseException] | None = None):
        """Initialize a Failure with an exception.
        
        Args:
            exc_value: The exception instance
            exc_type: The exception type (optional, inferred from exc_value if not provided)
        """
        if exc_value is None:
            import sys
            exc_value = sys.exc_info()[1]
            if exc_value is None:
                raise ValueError("Failure() with no exception")
        
        self.value: BaseException = exc_value
        self.type: type[BaseException] = exc_type or type(exc_value)
    
    def check(self, *exc_types: type[BaseException]) -> type[BaseException] | None:
        """Check if this failure's exception matches any of the given exception types.
        
        Args:
            *exc_types: Exception types to check against
            
        Returns:
            The exception type if it matches, None otherwise
        """
        for exc_type in exc_types:
            if isinstance(self.value, exc_type):
                return self.type
        return None
    
    def __repr__(self) -> str:
        return f"Failure({self.type.__name__}: {self.value})"


async def _defer_sleep() -> None:
    """Delay by _DEFER_DELAY so event loop has a chance to process pending tasks.

    It delays by 100ms to allow the event loop to handle other tasks,
    so do not set delay to zero.
    """
    await asyncio.sleep(_DEFER_DELAY)


async def parallel(
    iterable: Iterable[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], Awaitable[_T2]],  # noqa: A002
    *args: _P.args,
    **named: _P.kwargs,
) -> list[_T2]:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Args:
        iterable: Items to process
        count: Maximum number of concurrent tasks
        callable: Async function to call for each item
        *args: Additional positional arguments
        **named: Additional keyword arguments

    Returns:
        List of results from all calls
    """
    semaphore = asyncio.Semaphore(count)

    async def _process_item(item: _T) -> _T2:
        async with semaphore:
            return await callable(item, *args, **named)

    tasks = [asyncio.create_task(_process_item(item)) for item in iterable]
    return await asyncio.gather(*tasks)


async def parallel_async(
    async_iterable: AsyncIterator[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], Awaitable[_T2]],  # noqa: A002
    *args: _P.args,
    **named: _P.kwargs,
) -> list[_T2]:
    """Like ``parallel`` but for async iterators.

    Args:
        async_iterable: Async iterator of items to process
        count: Maximum number of concurrent tasks
        callable: Async function to call for each item
        *args: Additional positional arguments
        **named: Additional keyword arguments

    Returns:
        List of results from all calls
    """
    semaphore = asyncio.Semaphore(count)
    results: list[_T2] = []
    tasks: set[asyncio.Task[_T2]] = set()

    async def _process_item(item: _T) -> _T2:
        async with semaphore:
            return await callable(item, *args, **named)

    async for item in async_iterable:
        # If we have too many tasks, wait for some to complete
        while len(tasks) >= count:
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            results.extend([task.result() for task in done])

        task = asyncio.create_task(_process_item(item))
        tasks.add(task)

    # Wait for remaining tasks
    if tasks:
        done_tasks = await asyncio.gather(*tasks)
        results.extend(done_tasks)

    return results


async def process_chain(
    callbacks: Iterable[Callable[..., Awaitable[Any]]],
    input: Any,  # noqa: A002
    *a: Any,
    **kw: Any,
) -> Any:
    """Process a chain of async callbacks.

    Each callback receives the result of the previous one as its first argument,
    plus any additional args/kwargs.

    Args:
        callbacks: Sequence of async functions to call
        input: Initial input value
        *a: Additional positional arguments for each callback
        **kw: Additional keyword arguments for each callback

    Returns:
        The final result after all callbacks
    """
    result = input
    for callback in callbacks:
        result = await callback(result, *a, **kw)
    return result


async def process_parallel(
    callbacks: Iterable[Callable[Concatenate[_T, _P], Awaitable[_T2]]],
    input: _T,  # noqa: A002
    *a: _P.args,
    **kw: _P.kwargs,
) -> list[_T2]:
    """Return a list with the output of all successful calls to the given callbacks.

    Args:
        callbacks: Sequence of async functions to call
        input: Input value to pass to each callback
        *a: Additional positional arguments for each callback
        **kw: Additional keyword arguments for each callback

    Returns:
        List of results from all callbacks
    """
    tasks = [callback(input, *a, **kw) for callback in callbacks]
    return await asyncio.gather(*tasks)


def iter_errback(
    iterable: Iterable[_T],
    errback: Callable[Concatenate[BaseException, _P], Any],
    *a: _P.args,
    **kw: _P.kwargs,
) -> Iterable[_T]:
    """Wrap an iterable calling an errback if an error is caught while
    iterating it.

    Args:
        iterable: The iterable to wrap
        errback: Function to call with caught exceptions
        *a: Additional positional arguments for errback
        **kw: Additional keyword arguments for errback

    Yields:
        Items from the iterable
    """
    it = iter(iterable)
    while True:
        try:
            yield next(it)
        except StopIteration:
            break
        except Exception as e:
            errback(e, *a, **kw)


async def aiter_errback(
    aiterable: AsyncIterator[_T],
    errback: Callable[Concatenate[BaseException, _P], Any],
    *a: _P.args,
    **kw: _P.kwargs,
) -> AsyncIterator[_T]:
    """Wrap an async iterable calling an errback if an error is caught while
    iterating it. Similar to :func:`scrapy.utils.defer.iter_errback`.

    Args:
        aiterable: The async iterable to wrap
        errback: Function to call with caught exceptions
        *a: Additional positional arguments for errback
        **kw: Additional keyword arguments for errback

    Yields:
        Items from the async iterable
    """
    it = aiterable.__aiter__()
    while True:
        try:
            yield await it.__anext__()
        except StopAsyncIteration:
            break
        except Exception as e:
            errback(e, *a, **kw)


@overload
def deferred_from_coro(o: Awaitable[_T]) -> Future[_T]: ...


@overload
def deferred_from_coro(o: _T2) -> _T2: ...


def deferred_from_coro(o: Awaitable[_T] | _T2) -> Future[_T] | _T2:
    """Convert a coroutine or other awaitable object into a Future,
    or return the object as is if it isn't a coroutine.

    Args:
        o: An awaitable object or any other value

    Returns:
        A Future if o is awaitable, otherwise o unchanged
    """
    if isinstance(o, Future):
        return o
    if inspect.isawaitable(o):
        return asyncio.ensure_future(o)
    return o


def deferred_f_from_coro_f(
    coro_f: Callable[_P, Awaitable[_T]],
) -> Callable[_P, Future[_T]]:
    """Convert a coroutine function into a function that returns a Future.

    The coroutine function will be called at the time when the wrapper is called.
    Wrapper args will be passed to it.
    This is useful for callback chains, as callback functions are called with
    the previous callback result.

    Args:
        coro_f: A coroutine function

    Returns:
        A function that returns a Future
    """

    @wraps(coro_f)
    def f(*coro_args: _P.args, **coro_kwargs: _P.kwargs) -> Future[_T]:
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))

    return f


def maybeDeferred_coro(
    f: Callable[_P, Any], *args: _P.args, **kw: _P.kwargs
) -> Future[Any]:
    """Call a function and ensure the result is a Future.

    Handles functions that return:
    - Futures (returned as-is)
    - Awaitables (converted to Future)
    - Regular values (wrapped in a completed Future)
    - Exceptions (wrapped in a failed Future)

    Args:
        f: The function to call
        *args: Positional arguments for the function
        **kw: Keyword arguments for the function

    Returns:
        A Future representing the result
    """
    try:
        result = f(*args, **kw)
    except Exception as e:
        future: Future[Any] = asyncio.Future()
        future.set_exception(e)
        return future

    if isinstance(result, Future):
        return result
    if asyncio.isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    if isinstance(result, BaseException):
        future = asyncio.Future()
        future.set_exception(result)
        return future

    future = asyncio.Future()
    future.set_result(result)
    return future


def deferred_to_future(d: Future[_T]) -> Future[_T]:
    """Return an :class:`asyncio.Future` object.

    In pure asyncio, this is a no-op that just returns the Future as-is.
    This function exists for API compatibility.

    Args:
        d: A Future object

    Returns:
        The same Future object
    """
    return d


def maybe_deferred_to_future(d: Future[_T]) -> Future[_T]:
    """Return *d* as an awaitable Future.

    In pure asyncio, this is a no-op that just returns the Future as-is.
    This function exists for API compatibility.

    Args:
        d: A Future object

    Returns:
        The same Future object
    """
    return d


def _schedule_coro(coro: Coroutine[Any, Any, Any]) -> None:
    """Schedule the coroutine as a task.

    This doesn't store the reference to the task, so a better
    alternative is calling :func:`asyncio.create_task` or
    :func:`scrapy.utils.defer.deferred_from_coro`,
    keeping the result, and adding proper exception handling to it.

    Args:
        coro: The coroutine to schedule
    """
    loop = asyncio.get_event_loop()
    loop.create_task(coro)  # noqa: RUF006


@overload
def ensure_awaitable(o: Awaitable[_T]) -> Awaitable[_T]: ...


@overload
def ensure_awaitable(o: _T) -> Awaitable[_T]: ...


def ensure_awaitable(o: _T | Awaitable[_T]) -> Awaitable[_T]:
    """Convert any value to an awaitable object.

    For a :class:`asyncio.Future` object, return it as-is.
    For an awaitable object of a different type, return it as is.
    For any other value, return a coroutine that completes with that value.

    Args:
        o: Any value or awaitable

    Returns:
        An awaitable object
    """
    if isinstance(o, Future):
        return o
    if inspect.isawaitable(o):
        return o

    async def coro() -> _T:
        return o

    return coro()
