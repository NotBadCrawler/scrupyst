import scrapy
from scrapy.crawler import CrawlerProcess


class ReactorCheckExtension:
    def __init__(self):
        # In pure asyncio, asyncio is always available
        pass


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(
    settings={
        "EXTENSIONS": {ReactorCheckExtension: 0},
    }
)
process.crawl(NoRequestsSpider)
process.start()
