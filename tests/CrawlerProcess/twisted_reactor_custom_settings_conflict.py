import scrapy
from scrapy.crawler import CrawlerProcess


class SelectReactorSpider(scrapy.Spider):
    name = "select_reactor"


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"


process = CrawlerProcess()
process.crawl(SelectReactorSpider)
process.crawl(AsyncioReactorSpider)
process.start()
