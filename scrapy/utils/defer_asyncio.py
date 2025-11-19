"""
Helper functions for dealing with asyncio tasks and futures.
This module replaces the Twisted defer.py module with pure asyncio equivalents.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_T = TypeVar("_T")
_T2 = TypeVar("_T2")
_P = ParamSpec("_P")

_DEFER_DELAY = 0.1


async def defer_fail(exception: BaseException) -> None:
    """Delay raising an exception until the next event loop iteration.
    
    Args:
        exception: The exception to raise
        
    Raises:
        The provided exception after a delay
    """
    await asyncio.sleep(_DEFER_DELAY)
    raise exception


async def defer_succeed(result: _T) -> _T:
    """Delay returning a result until the next event loop iteration.
    
    Args:
        result: The value to return
        
    Returns:
        The provided result after a delay
    """
    await asyncio.sleep(_DEFER_DELAY)
    return result


async def defer_result(result: Any) -> Any:
    """Delay returning a result or raising an exception.
    
    Args:
        result: A value or exception to handle
        
    Returns:
        The result if it's not an exception
        
    Raises:
        The exception if result is an exception
    """
    await asyncio.sleep(_DEFER_DELAY)
    if isinstance(result, BaseException):
        raise result
    return result


@overload
def ensure_awaitable(
    f: Callable[_P, Awaitable[_T]], *args: _P.args, **kw: _P.kwargs
) -> Awaitable[_T]: ...


@overload
def ensure_awaitable(
    f: Callable[_P, _T], *args: _P.args, **kw: _P.kwargs
) -> Awaitable[_T]: ...


def ensure_awaitable(
    f: Callable[_P, Awaitable[_T] | _T],
    *args: _P.args,
    **kw: _P.kwargs,
) -> Awaitable[_T]:
    """Ensure a function call returns an awaitable.
    
    If the function returns an awaitable, return it as-is.
    If the function returns a regular value, wrap it in a coroutine.
    If the function raises an exception, wrap it in a failed coroutine.
    
    Args:
        f: The function to call
        *args: Positional arguments for the function
        **kw: Keyword arguments for the function
        
    Returns:
        An awaitable that will resolve to the function's result
    """
    try:
        result = f(*args, **kw)
    except Exception as e:
        async def _raise_exception():
            raise e
        return _raise_exception()
    
    if inspect.isawaitable(result) or asyncio.isfuture(result):
        return result  # type: ignore[return-value]
    
    async def _return_value():
        return result  # type: ignore[return-value]
    return _return_value()


async def parallel(
    iterable: Iterable[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], Awaitable[_T2]],  # noqa: A002
    *args: _P.args,
    **named: _P.kwargs,
) -> list[_T2]:
    """Execute a callable over objects in an iterable, in parallel.
    
    Uses no more than ``count`` concurrent calls.
    
    Args:
        iterable: The items to process
        count: Maximum number of concurrent tasks
        callable: The async function to call for each item
        *args: Additional positional arguments for callable
        **named: Additional keyword arguments for callable
        
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
        async_iterable: The async iterator of items to process
        count: Maximum number of concurrent tasks
        callable: The async function to call for each item
        *args: Additional positional arguments for callable
        **named: Additional keyword arguments for callable
        
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


def process_chain(
    callbacks: Iterable[Callable[..., Awaitable[Any]]], input: Any, *args: Any, **kwargs: Any  # noqa: A002
) -> Awaitable[Any]:
    """Process a chain of async callbacks.
    
    Each callback receives the result of the previous one as its first argument,
    plus any additional args/kwargs.
    
    Args:
        callbacks: Sequence of async functions to call
        input: Initial input value
        *args: Additional positional arguments for each callback
        **kwargs: Additional keyword arguments for each callback
        
    Returns:
        Awaitable that resolves to the final result
    """
    async def _process() -> Any:
        result = input
        for callback in callbacks:
            result = await callback(result, *args, **kwargs)
        return result
    
    return _process()


def process_chain_both(
    callbacks: Iterable[tuple[Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]]],
    input: Any,  # noqa: A002
    *args: Any,
    **kwargs: Any,
) -> Awaitable[Any]:
    """Process a chain of async callback pairs (success, error).
    
    Each pair contains (callback, errback). If the callback succeeds, its result
    is passed to the next callback. If it raises an exception, the errback is called.
    
    Args:
        callbacks: Sequence of (callback, errback) pairs
        input: Initial input value
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
        
    Returns:
        Awaitable that resolves to the final result
    """
    async def _process() -> Any:
        result: Any = input
        exception: BaseException | None = None
        
        for callback, errback in callbacks:
            try:
                if exception is not None:
                    result = await errback(exception, *args, **kwargs)
                    exception = None
                else:
                    result = await callback(result, *args, **kwargs)
            except BaseException as e:
                exception = e
        
        if exception is not None:
            raise exception
        return result
    
    return _process()
