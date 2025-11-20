"""Aiohttp-based HTTP mock server for tests.

This is the asyncio replacement for the Twisted-based HTTP mock server.
"""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from tests import tests_datadir

from .http_base_aiohttp import BaseMockServerAiohttp, main_factory_aiohttp
from .http_resources_aiohttp import (
    compress_handler,
    delay_handler,
    echo_handler,
    encoding_handler,
    follow_handler,
    forever_handler,
    host_handler,
    html_handler,
    numbers_handler,
    partial_handler,
    payload_handler,
    redirect_handler,
    redirect_to_handler,
    redirected_handler,
    set_cookie_handler,
    status_handler,
    text_handler,
)


def create_app() -> web.Application:
    """Create the main mock server application."""
    app = web.Application()
    
    # Add all routes
    app.router.add_get("/status", status_handler)
    app.router.add_get("/follow", follow_handler)
    app.router.add_get("/delay", delay_handler)
    app.router.add_get("/partial", partial_handler)
    # app.router.add_get("/drop", drop_handler)  # TODO: implement
    # app.router.add_get("/raw", raw_handler)  # TODO: implement
    app.router.add_get("/echo", echo_handler)
    app.router.add_post("/echo", echo_handler)
    app.router.add_post("/payload", payload_handler)
    # app.router.add_post("/alpayload", arbitrary_length_payload_handler)  # TODO
    
    # Static files
    static_path = Path(tests_datadir) / "test_site"
    app.router.add_static("/static", static_path)
    
    # Simple content
    app.router.add_get("/redirect-to", redirect_to_handler)
    app.router.add_get("/text", text_handler)
    app.router.add_get("/html", html_handler)
    app.router.add_get("/enc-gb18030", encoding_handler)
    app.router.add_get("/redirect", redirect_handler)
    # app.router.add_get("/redirect-no-meta-refresh", no_meta_refresh_redirect_handler)  # TODO
    app.router.add_get("/redirected", redirected_handler)
    app.router.add_get("/numbers", numbers_handler)
    app.router.add_get("/wait", forever_handler)
    app.router.add_get("/hang-after-headers", forever_handler)
    app.router.add_get("/host", host_handler)
    # app.router.add_get("/broken", broken_download_handler)  # TODO
    # app.router.add_get("/chunked", chunked_handler)  # TODO
    # app.router.add_get("/broken-chunked", broken_chunked_handler)  # TODO
    # app.router.add_get("/contentlength", content_length_header_handler)  # TODO
    # app.router.add_get("/nocontenttype", empty_content_type_handler)  # TODO
    # app.router.add_get("/largechunkedfile", large_chunked_file_handler)  # TODO
    app.router.add_get("/compress", compress_handler)
    # app.router.add_get("/duplicate-header", duplicate_header_handler)  # TODO
    # app.router.add_get("/response-headers", response_headers_handler)  # TODO
    app.router.add_get("/set-cookie", set_cookie_handler)
    
    # Default handler
    async def default_handler(request):
        return web.Response(text="Scrapy mock HTTP server (aiohttp)\n")
    
    app.router.add_get("/", default_handler)
    
    return app


class MockServer(BaseMockServerAiohttp):
    module_name = "tests.mockserver.http_aiohttp"


main = main_factory_aiohttp(create_app)


if __name__ == "__main__":
    main()
