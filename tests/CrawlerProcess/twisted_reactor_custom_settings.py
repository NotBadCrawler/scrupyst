import scrapy
from scrapy.crawler import CrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"


process = CrawlerProcess()
process.crawl(AsyncioReactorSpider)
process.start()
