"""Helper functions for working with signals"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from collections.abc import Sequence
from typing import Any as TypingAny

from pydispatch.dispatcher import (
    Anonymous,
    Any,
    disconnect,
    getAllReceivers,
    liveReceivers,
)
from pydispatch.robustapply import robustApply

from scrapy.exceptions import StopDownload

logger = logging.getLogger(__name__)


def send_catch_log(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like ``pydispatcher.robust.sendRobust()`` but it also logs errors and returns
    exceptions instead of raising them.
    """
    from scrapy.utils.defer import Failure
    
    dont_log = named.pop("dont_log", ())
    dont_log = tuple(dont_log) if isinstance(dont_log, Sequence) else (dont_log,)
    dont_log += (StopDownload,)
    spider = named.get("spider")
    responses: list[tuple[TypingAny, TypingAny]] = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        result: TypingAny
        try:
            response = robustApply(
                receiver, signal=signal, sender=sender, *arguments, **named
            )
            # Check if it's a coroutine or awaitable
            if inspect.iscoroutine(response) or inspect.isawaitable(response):
                logger.error(
                    "Cannot return coroutines from synchronous signal handler: %(receiver)s",
                    {"receiver": receiver},
                    extra={"spider": spider},
                )
                # Close the coroutine to avoid warnings
                if inspect.iscoroutine(response):
                    response.close()
                result = None
            else:
                result = response
        except dont_log as e:
            result = Failure(e)
        except Exception as e:
            result = Failure(e)
            logger.error(
                "Error caught on signal handler: %(receiver)s",
                {"receiver": receiver},
                exc_info=True,
                extra={"spider": spider},
            )
        responses.append((receiver, result))
    return responses


async def send_catch_log_deferred(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like :func:`send_catch_log` but supports :ref:`asynchronous signal handlers
    <signal-deferred>`.

    Returns a coroutine that completes once all signal handlers have finished.
    """
    from scrapy.utils.defer import Failure

    async def call_handler(receiver: TypingAny) -> tuple[TypingAny, TypingAny]:
        """Call a signal handler and handle errors."""
        try:
            response = robustApply(
                receiver, signal=signal, sender=sender, *arguments, **named
            )
            # If it's a coroutine or awaitable, await it
            if inspect.iscoroutine(response) or inspect.isawaitable(response):
                result = await response
            else:
                result = response
            return (receiver, result)
        except Exception as e:
            if dont_log is None or not isinstance(e, dont_log):
                logger.error(
                    "Error caught on signal handler: %(receiver)s",
                    {"receiver": receiver},
                    exc_info=sys.exc_info(),
                    extra={"spider": spider},
                )
            return (receiver, Failure(e))

    dont_log = named.pop("dont_log", None)
    spider = named.get("spider")
    tasks = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        tasks.append(call_handler(receiver))

    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


async def send_catch_log_async(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like :func:`send_catch_log` but supports :ref:`asynchronous signal handlers
    <signal-deferred>`.

    Returns a coroutine that completes once all signal handlers have finished.

    .. versionadded:: VERSION
    """
    return await send_catch_log_deferred(signal, sender, *arguments, **named)


def disconnect_all(signal: TypingAny = Any, sender: TypingAny = Any) -> None:
    """Disconnect all signal handlers. Useful for cleaning up after running
    tests.
    """
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        disconnect(receiver, signal=signal, sender=sender)
