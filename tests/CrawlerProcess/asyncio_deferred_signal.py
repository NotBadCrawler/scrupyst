from __future__ import annotations

import asyncio
import sys

from scrapy import Spider
from scrapy.crawler import CrawlerProcess


class UppercasePipeline:
    async def _open_spider(self, spider):
        spider.logger.info("async pipeline opened!")
        await asyncio.sleep(0.1)

    async def open_spider(self, spider):
        await self._open_spider(spider)

    def process_item(self, item):
        return {"url": item["url"].upper()}


class UrlSpider(Spider):
    name = "url_spider"
    start_urls = ["data:,"]
    custom_settings = {
        "ITEM_PIPELINES": {UppercasePipeline: 100},
    }

    def parse(self, response):
        yield {"url": response.url}


if __name__ == "__main__":
    ASYNCIO_EVENT_LOOP: str | None
    try:
        ASYNCIO_EVENT_LOOP = sys.argv[1]
    except IndexError:
        ASYNCIO_EVENT_LOOP = None

    process = CrawlerProcess(
        settings={
            "ASYNCIO_EVENT_LOOP": ASYNCIO_EVENT_LOOP,
        }
    )
    process.crawl(UrlSpider)
    process.start()
