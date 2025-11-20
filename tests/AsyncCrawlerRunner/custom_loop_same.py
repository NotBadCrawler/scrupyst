import asyncio

import uvloop

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    custom_settings = {
        "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
    }

    async def start(self):
        return
        yield


async def main():
    configure_logging()
    runner = AsyncCrawlerRunner()
    await runner.crawl(NoRequestsSpider)


uvloop.install()
asyncio.run(main())
