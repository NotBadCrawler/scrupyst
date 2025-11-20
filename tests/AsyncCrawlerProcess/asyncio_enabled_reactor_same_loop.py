import asyncio
import sys

from uvloop import Loop

import scrapy
from scrapy.crawler import AsyncCrawlerProcess

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.set_event_loop(Loop())


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
    }
)
process.crawl(NoRequestsSpider)
process.start()
