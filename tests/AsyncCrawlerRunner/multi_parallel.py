import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


async def main():
    configure_logging()
    runner = AsyncCrawlerRunner()
    runner.crawl(NoRequestsSpider)
    runner.crawl(NoRequestsSpider)
    await runner.join()


asyncio.run(main())
