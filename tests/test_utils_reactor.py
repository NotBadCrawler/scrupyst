import asyncio
import warnings

import pytest

from scrapy.utils.reactor import (
    _asyncio_reactor_path,
    install_reactor,
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)


class TestAsyncio:
    def test_is_asyncio_reactor_installed(self) -> None:
        # In pure asyncio mode, this should always return True
        assert is_asyncio_reactor_installed() is True

    def test_install_asyncio_reactor(self):
        with warnings.catch_warnings(record=True) as w:
            install_reactor(_asyncio_reactor_path)
            assert len(w) == 0, [str(warning) for warning in w]

    async def test_set_asyncio_event_loop(self):
        install_reactor(_asyncio_reactor_path)
        assert set_asyncio_event_loop(None) is asyncio.get_running_loop()
