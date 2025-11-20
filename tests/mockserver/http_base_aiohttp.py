"""Base classes and functions for aiohttp-based HTTP mockservers."""

from __future__ import annotations

import argparse
import asyncio
import ssl
import sys
from abc import ABC, abstractmethod
from subprocess import PIPE, Popen
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from aiohttp import web

from tests.utils import get_script_run_env

from .utils import ssl_context_factory_aiohttp

if TYPE_CHECKING:
    from collections.abc import Callable


class BaseMockServerAiohttp(ABC):
    listen_http: bool = True
    listen_https: bool = True

    @property
    @abstractmethod
    def module_name(self) -> str:
        raise NotImplementedError

    def __init__(self) -> None:
        if not self.listen_http and not self.listen_https:
            raise ValueError("At least one of listen_http and listen_https must be set")

        self.proc: Popen | None = None
        self.host: str = "127.0.0.1"
        self.http_port: int | None = None
        self.https_port: int | None = None

    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", self.module_name, *self.get_additional_args()],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        if self.listen_http:
            http_address = self.proc.stdout.readline().strip().decode("ascii")
            http_parsed = urlparse(http_address)
            self.http_port = http_parsed.port
        if self.listen_https:
            https_address = self.proc.stdout.readline().strip().decode("ascii")
            https_parsed = urlparse(https_address)
            self.https_port = https_parsed.port
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.proc:
            self.proc.kill()
            self.proc.communicate()

    def get_additional_args(self) -> list[str]:
        return []

    def port(self, is_secure: bool = False) -> int:
        if not is_secure and not self.listen_http:
            raise ValueError("This server doesn't provide HTTP")
        if is_secure and not self.listen_https:
            raise ValueError("This server doesn't provide HTTPS")
        port = self.https_port if is_secure else self.http_port
        assert port is not None
        return port

    def url(self, path: str, is_secure: bool = False) -> str:
        port = self.port(is_secure)
        scheme = "https" if is_secure else "http"
        return f"{scheme}://{self.host}:{port}{path}"


def main_factory_aiohttp(
    app_factory: Callable[[], web.Application],
    *,
    listen_http: bool = True,
    listen_https: bool = True,
) -> Callable[[], None]:
    if not listen_http and not listen_https:
        raise ValueError("At least one of listen_http and listen_https must be set")

    def main() -> None:
        async def run_server():
            app = app_factory()
            runner = web.AppRunner(app)
            await runner.setup()

            sites = []

            if listen_http:
                http_site = web.TCPSite(runner, "127.0.0.1", 0)
                await http_site.start()
                sites.append(http_site)
                # Get the actual port
                for site in runner._sites:
                    if isinstance(site, web.TCPSite) and site._ssl_context is None:
                        http_port = site._server.sockets[0].getsockname()[1]
                        print(f"http://127.0.0.1:{http_port}")
                        break

            if listen_https:
                parser = argparse.ArgumentParser()
                parser.add_argument("--keyfile", help="SSL key file")
                parser.add_argument("--certfile", help="SSL certificate file")
                parser.add_argument(
                    "--cipher-string",
                    default=None,
                    help="SSL cipher string (optional)",
                )
                args = parser.parse_args()
                context_factory_kw = {}
                if args.keyfile:
                    context_factory_kw["keyfile"] = args.keyfile
                if args.certfile:
                    context_factory_kw["certfile"] = args.certfile
                if args.cipher_string:
                    context_factory_kw["cipher_string"] = args.cipher_string
                ssl_context = ssl_context_factory_aiohttp(**context_factory_kw)
                https_site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=ssl_context)
                await https_site.start()
                sites.append(https_site)
                # Get the actual port
                for site in runner._sites:
                    if isinstance(site, web.TCPSite) and site._ssl_context is not None:
                        https_port = site._server.sockets[0].getsockname()[1]
                        print(f"https://127.0.0.1:{https_port}")
                        break

            # Keep the server running
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                pass
            finally:
                await runner.cleanup()

        asyncio.run(run_server())

    return main
