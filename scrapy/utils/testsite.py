import asyncio
import warnings
from typing import Any
from urllib.parse import urljoin

from aiohttp import web

from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.utils.testsite module is deprecated.",
    ScrapyDeprecationWarning,
)


class SiteTest:
    async def setUp(self) -> None:
        """Set up test site with aiohttp web server."""
        super().setUp()  # type: ignore[misc]
        app = await test_site()
        runner = web.AppRunner(app)
        await runner.setup()
        # Use port 0 to let OS assign an available port
        self.site = web.TCPSite(runner, "127.0.0.1", 0)
        await self.site.start()
        # Get the actual port that was assigned
        assert runner.addresses
        port = runner.addresses[0][1]
        self.baseurl = f"http://localhost:{port}/"
        self._runner = runner

    async def tearDown(self) -> None:
        """Tear down test site."""
        super().tearDown()  # type: ignore[misc]
        await self._runner.cleanup()

    def url(self, path: str) -> str:
        return urljoin(self.baseurl, path)


async def handle_text(request: web.Request) -> web.Response:
    """Handle /text endpoint."""
    return web.Response(text="Works", content_type="text/plain")


async def handle_html(request: web.Request) -> web.Response:
    """Handle /html endpoint."""
    return web.Response(
        text="<body><p class='one'>Works</p><p class='two'>World</p></body>",
        content_type="text/html",
    )


async def handle_enc_gb18030(request: web.Request) -> web.Response:
    """Handle /enc-gb18030 endpoint."""
    return web.Response(
        body=b"<p>gb18030 encoding</p>",
        content_type="text/html; charset=gb18030",
    )


async def handle_redirect(request: web.Request) -> web.Response:
    """Handle /redirect endpoint with meta refresh."""
    raise web.HTTPFound("/redirected")


async def handle_redirect_no_meta(request: web.Request) -> web.Response:
    """Handle /redirect-no-meta-refresh endpoint without meta refresh."""
    # Return redirect without meta refresh tag
    response = web.Response(
        status=302,
        headers={"Location": "/redirected"},
    )
    return response


async def handle_redirected(request: web.Request) -> web.Response:
    """Handle /redirected endpoint."""
    return web.Response(text="Redirected here", content_type="text/plain")


async def test_site() -> web.Application:
    """Create test web application."""
    app = web.Application()
    app.router.add_get("/text", handle_text)
    app.router.add_get("/html", handle_html)
    app.router.add_get("/enc-gb18030", handle_enc_gb18030)
    app.router.add_get("/redirect", handle_redirect)
    app.router.add_get("/redirect-no-meta-refresh", handle_redirect_no_meta)
    app.router.add_get("/redirected", handle_redirected)
    return app


async def main() -> None:
    """Run test site server."""
    app = await test_site()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    assert runner.addresses
    port = runner.addresses[0][1]
    print(f"http://localhost:{port}/")
    # Keep server running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
