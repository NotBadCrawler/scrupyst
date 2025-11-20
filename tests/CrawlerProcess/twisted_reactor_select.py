import scrapy
from scrapy.crawler import CrawlerProcess


class SelectReactorSpider(scrapy.Spider):
    name = "select_reactor"


process = CrawlerProcess(settings={})
process.crawl(SelectReactorSpider)
process.start()
