# ruff: noqa: E402

import asyncio

from tests.mockserver.dns_aiohttp import MockDNSServer
from tests.mockserver.http_aiohttp import MockServer

from scrapy import Request, Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.log import configure_logging


class LocalhostSpider(Spider):
    name = "localhost_spider"

    async def start(self):
        yield Request(self.url)

    def parse(self, response):
        netloc = urlparse_cached(response).netloc
        host = netloc.split(":")[0]
        self.logger.info(f"Host: {host}")
        self.logger.info(f"Type: {type(response.ip_address)}")
        self.logger.info(f"IP address: {response.ip_address}")


async def main():
    async with MockServer() as mock_http_server, MockDNSServer() as mock_dns_server:
        port = mock_http_server.http_port
        url = f"http://not.a.real.domain:{port}/echo"

        # Configure DNS resolver for asyncio
        # Note: asyncio doesn't have a direct equivalent to twisted's installResolver
        # We may need to configure system DNS or use custom resolver settings

        configure_logging()
        runner = CrawlerRunner()
        await runner.crawl(LocalhostSpider, url=url)


if __name__ == "__main__":
    asyncio.run(main())
