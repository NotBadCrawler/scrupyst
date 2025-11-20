import sys
from pathlib import Path
from subprocess import PIPE, Popen


class TestCmdlineCrawlPipeline:
    def _execute(self, spname):
        args = (sys.executable, "-m", "scrapy.cmdline", "crawl", spname)
        cwd = Path(__file__).resolve().parent
        proc = Popen(args, stdout=PIPE, stderr=PIPE, cwd=cwd)
        _, stderr = proc.communicate()
        return proc.returncode, stderr

    def test_open_spider_normally_in_pipeline(self):
        returncode, _ = self._execute("normal")
        assert returncode == 0

    def test_exception_at_open_spider_in_pipeline(self):
        returncode, stderr = self._execute("exception")
        # An unhandled exception in a pipeline should not stop the crawl
        assert returncode == 0
        # With asyncio (no Twisted), modern traceback format is used
        assert b'RuntimeError("exception")' in stderr or b"RuntimeError: exception" in stderr
