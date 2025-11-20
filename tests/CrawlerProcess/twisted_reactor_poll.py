import scrapy
from scrapy.crawler import CrawlerProcess


class PollReactorSpider(scrapy.Spider):
    name = "poll_reactor"


process = CrawlerProcess(settings={})
process.crawl(PollReactorSpider)
process.start()
