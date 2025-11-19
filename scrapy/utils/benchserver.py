import asyncio
import random
from typing import Any
from urllib.parse import urlencode

from aiohttp import web


async def handle_root(request: web.Request) -> web.Response:
    """Handle root and follow endpoints."""
    total = _getarg(request, "total", 100, int)
    show = _getarg(request, "show", 10, int)
    nlist = [random.randint(1, total) for _ in range(show)]  # noqa: S311
    
    html_parts = ["<html><head></head><body>"]
    
    # Get current query parameters
    query_params = dict(request.query)
    
    for nl in nlist:
        query_params["n"] = str(nl)
        argstr = urlencode(query_params, doseq=True)
        html_parts.append(f"<a href='/follow?{argstr}'>follow {nl}</a><br>")
    
    html_parts.append("</body></html>")
    
    return web.Response(
        text="".join(html_parts),
        content_type="text/html",
    )


def _getarg(request: web.Request, name: str, default: Any = None, type_: type = str) -> Any:
    """Get argument from request query parameters."""
    value = request.query.get(name)
    if value is None:
        return default
    return type_(value)


async def create_app() -> web.Application:
    """Create the benchmark server application."""
    app = web.Application()
    # Handle both root and /follow routes with the same handler
    app.router.add_get("/", handle_root)
    app.router.add_get("/follow", handle_root)
    return app


async def main() -> None:
    """Run the benchmark server."""
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8998)
    await site.start()
    
    print(f"Bench server at http://127.0.0.1:8998")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
