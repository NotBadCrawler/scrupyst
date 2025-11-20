# This is only used by tests.test_downloader_handlers_http_base.TestSimpleHttpsBase

from __future__ import annotations

from aiohttp import web

from .http_base_aiohttp import BaseMockServerAiohttp, main_factory_aiohttp


def create_app() -> web.Application:
    """Create simple HTTPS app with a single /file endpoint."""
    app = web.Application()
    
    async def file_handler(request: web.Request) -> web.Response:
        """Return static file content."""
        return web.Response(body=b"0123456789", content_type="text/plain")
    
    async def default_handler(request: web.Request) -> web.Response:
        """Default handler for all other routes."""
        return web.Response(body=b"", content_type="text/plain")
    
    app.router.add_get("/file", file_handler)
    app.router.add_get("/", default_handler)
    # Catch-all route
    app.router.add_route("*", "/{path:.*}", default_handler)
    
    return app


class SimpleMockServer(BaseMockServerAiohttp):
    listen_http = False
    module_name = "tests.mockserver.simple_https_aiohttp"

    def __init__(self, keyfile: str, certfile: str, cipher_string: str | None):
        super().__init__()
        self.keyfile = keyfile
        self.certfile = certfile
        self.cipher_string = cipher_string or ""

    def get_additional_args(self) -> list[str]:
        args = [
            "--keyfile",
            self.keyfile,
            "--certfile",
            self.certfile,
        ]
        if self.cipher_string is not None:
            args.extend(["--cipher-string", self.cipher_string])
        return args


main = main_factory_aiohttp(create_app, listen_http=False)


if __name__ == "__main__":
    main()
