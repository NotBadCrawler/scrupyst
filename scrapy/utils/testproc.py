from __future__ import annotations

import asyncio
import os
import sys
import warnings
from typing import TYPE_CHECKING

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from asyncio import Future
    from collections.abc import Iterable


warnings.warn(
    "The scrapy.utils.testproc module is deprecated.",
    ScrapyDeprecationWarning,
)


class ProcessTest:
    command: str | None = None
    prefix = [sys.executable, "-m", "scrapy.cmdline"]
    cwd = os.getcwd()  # trial chdirs to temp dir  # noqa: PTH109

    async def execute(
        self,
        args: Iterable[str],
        check_code: bool = True,
        settings: str | None = None,
    ) -> tuple[int, bytes, bytes]:
        env = os.environ.copy()
        if settings is not None:
            env["SCRAPY_SETTINGS_MODULE"] = settings
        assert self.command
        cmd = [*self.prefix, self.command, *args]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.cwd,
        )
        
        stdout, stderr = await process.communicate()
        exitcode = process.returncode or 0
        
        if exitcode and check_code:
            msg = f"process {cmd} exit with code {exitcode}"
            msg += f"\n>>> stdout <<<\n{stdout.decode()}"
            msg += "\n"
            msg += f"\n>>> stderr <<<\n{stderr.decode()}"
            raise RuntimeError(msg)
        return exitcode, stdout, stderr


class TestProcessProtocol:
    """Deprecated protocol class kept for backwards compatibility."""
    
    def __init__(self) -> None:
        self.future: Future[TestProcessProtocol] = asyncio.Future()
        self.out: bytes = b""
        self.err: bytes = b""
        self.exitcode: int | None = None

    def outReceived(self, data: bytes) -> None:
        self.out += data

    def errReceived(self, data: bytes) -> None:
        self.err += data

    def processEnded(self, exitcode: int) -> None:
        self.exitcode = exitcode
        if not self.future.done():
            self.future.set_result(self)
