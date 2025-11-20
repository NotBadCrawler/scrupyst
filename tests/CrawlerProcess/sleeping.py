import asyncio
import sys

import scrapy
from scrapy.crawler import CrawlerProcess


class SleepingSpider(scrapy.Spider):
    name = "sleeping"

    start_urls = ["data:,;"]

    async def parse(self, response):
        await asyncio.sleep(int(sys.argv[1]))


process = CrawlerProcess(settings={})

process.crawl(SleepingSpider)
process.start()
