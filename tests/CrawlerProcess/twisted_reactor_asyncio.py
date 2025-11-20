import scrapy
from scrapy.crawler import CrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"


process = CrawlerProcess(settings={})
process.crawl(AsyncioReactorSpider)
process.start()
