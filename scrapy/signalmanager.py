from __future__ import annotations

import asyncio
from typing import Any

from pydispatch import dispatcher

from scrapy.utils import signal as _signal


class SignalManager:
    def __init__(self, sender: Any = dispatcher.Anonymous):
        self.sender: Any = sender

    def connect(self, receiver: Any, signal: Any, **kwargs: Any) -> None:
        """
        Connect a receiver function to a signal.

        The signal can be any object, although Scrapy comes with some
        predefined signals that are documented in the :ref:`topics-signals`
        section.

        :param receiver: the function to be connected
        :type receiver: collections.abc.Callable

        :param signal: the signal to connect to
        :type signal: object
        """
        kwargs.setdefault("sender", self.sender)
        dispatcher.connect(receiver, signal, **kwargs)

    def disconnect(self, receiver: Any, signal: Any, **kwargs: Any) -> None:
        """
        Disconnect a receiver function from a signal. This has the
        opposite effect of the :meth:`connect` method, and the arguments
        are the same.
        """
        kwargs.setdefault("sender", self.sender)
        dispatcher.disconnect(receiver, signal, **kwargs)

    def send_catch_log(self, signal: Any, **kwargs: Any) -> list[tuple[Any, Any]]:
        """
        Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).
        """
        kwargs.setdefault("sender", self.sender)
        return _signal.send_catch_log(signal, **kwargs)

    async def send_catch_log_deferred(
        self, signal: Any, **kwargs: Any
    ) -> list[tuple[Any, Any]]:
        """
        Like :meth:`send_catch_log` but supports :ref:`asynchronous signal
        handlers <signal-deferred>`.

        Returns an awaitable that completes once all signal handlers
        have finished. Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).
        """
        kwargs.setdefault("sender", self.sender)
        return await _signal.send_catch_log_async(signal, **kwargs)

    async def send_catch_log_async(
        self, signal: Any, **kwargs: Any
    ) -> list[tuple[Any, Any]]:
        """
        Like :meth:`send_catch_log` but supports :ref:`asynchronous signal
        handlers <signal-deferred>`.

        Returns a coroutine that completes once all signal handlers
        have finished. Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).

        .. versionadded:: VERSION
        """
        kwargs.setdefault("sender", self.sender)
        return await _signal.send_catch_log_async(signal, **kwargs)

    def disconnect_all(self, signal: Any, **kwargs: Any) -> None:
        """
        Disconnect all receivers from the given signal.

        :param signal: the signal to disconnect from
        :type signal: object
        """
        kwargs.setdefault("sender", self.sender)
        _signal.disconnect_all(signal, **kwargs)

    async def wait_for(self, signal):
        """Await the next *signal*.

        See :ref:`start-requests-lazy` for an example.
        """
        future: asyncio.Future[None] = asyncio.Future()

        def handle():
            self.disconnect(handle, signal)
            if not future.done():
                future.set_result(None)

        self.connect(handle, signal)
        await future
