import asyncio
import sys

import scrapy
from scrapy.crawler import CrawlerProcess

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(
    settings={
        "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
    }
)
process.crawl(NoRequestsSpider)
process.start()
