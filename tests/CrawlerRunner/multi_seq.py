import asyncio

from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


async def main():
    configure_logging()
    runner = CrawlerRunner()
    await runner.crawl(NoRequestsSpider)
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
