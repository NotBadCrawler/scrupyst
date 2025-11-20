# This is only used by tests.test_downloader_handlers_http_base.TestHttpProxyBase

from __future__ import annotations

from .http_base_aiohttp import BaseMockServerAiohttp, main_factory_aiohttp
from .http_resources_aiohttp import uri_handler


def create_app():
    """Create proxy echo app with only URI handler."""
    from aiohttp import web
    
    app = web.Application()
    # Route all requests to uri_handler
    app.router.add_route("*", "/{path:.*}", uri_handler)
    return app


class ProxyEchoMockServer(BaseMockServerAiohttp):
    module_name = "tests.mockserver.proxy_echo_aiohttp"


main = main_factory_aiohttp(create_app)


if __name__ == "__main__":
    main()
