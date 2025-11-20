import scrapy
from scrapy.crawler import CrawlerProcess


class AsyncioReactorSpider1(scrapy.Spider):
    name = "asyncio_reactor1"


class AsyncioReactorSpider2(scrapy.Spider):
    name = "asyncio_reactor2"


process = CrawlerProcess()
process.crawl(AsyncioReactorSpider1)
process.crawl(AsyncioReactorSpider2)
process.start()
