"""Aiohttp-based HTTP resources for mock server.

This is a work-in-progress migration from Twisted-based resources.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import random
from urllib.parse import urlencode

from aiohttp import web

from scrapy.utils.python import to_bytes, to_unicode


def getarg(request: web.Request, name: str, default=None, type_=None):
    """Get query argument from aiohttp request."""
    if name in request.query:
        value = request.query[name]
        if type_ is not None:
            value = type_(value)
        return value
    return default


# Simple Resources (No async operations)


async def status_handler(request: web.Request) -> web.Response:
    """Return HTTP status code from query parameter 'n'."""
    n = getarg(request, "n", 200, type_=int)
    return web.Response(status=n, body=b"")


async def host_handler(request: web.Request) -> web.Response:
    """Echo the Host header value."""
    host = request.headers.get("Host", "")
    return web.Response(body=host.encode())


async def payload_handler(request: web.Request) -> web.Response:
    """Validate request body is exactly 100 bytes."""
    data = await request.read()
    content_length = request.headers.get("Content-Length", "0")
    if len(data) != 100 or int(content_length) != 100:
        return web.Response(body=b"ERROR")
    return web.Response(body=data)


async def echo_handler(request: web.Request) -> web.Response:
    """Echo request body back."""
    data = await request.read()
    return web.Response(body=data)


async def partial_handler(request: web.Request) -> web.Response:
    """Return partial content (HTTP 206)."""
    data = b"0123456789" * 1000  # 10KB of data
    range_header = request.headers.get("Range", "")
    
    if range_header and range_header.startswith("bytes="):
        # Parse range
        range_spec = range_header[6:]  # Remove "bytes="
        start, end = range_spec.split("-")
        start = int(start) if start else 0
        end = int(end) if end else len(data) - 1
        
        partial_data = data[start:end + 1]
        headers = {
            "Content-Range": f"bytes {start}-{end}/{len(data)}",
            "Content-Length": str(len(partial_data)),
        }
        return web.Response(status=206, body=partial_data, headers=headers)
    
    return web.Response(body=data)


async def text_handler(request: web.Request) -> web.Response:
    """Return plain text response."""
    return web.Response(body=b"Works", content_type="text/plain")


async def html_handler(request: web.Request) -> web.Response:
    """Return HTML response."""
    html = b"<body><p class='one'>Works</p><p class='two'>World</p></body>"
    return web.Response(body=html, content_type="text/html")


async def encoding_handler(request: web.Request) -> web.Response:
    """Return response with specific encoding."""
    return web.Response(
        body=b"<p>gb18030 encoding</p>",
        content_type="text/html; charset=gb18030"
    )


# Async Resources (With delays)


async def delay_handler(request: web.Request) -> web.Response:
    """Delay response by 'n' seconds."""
    n = getarg(request, "n", 1, type_=float)
    b = getarg(request, "b", 1, type_=int)
    
    response = web.StreamResponse()
    
    if b:
        # Send headers immediately, delay body
        await response.prepare(request)
        await asyncio.sleep(n)
        await response.write(to_bytes(f"Response delayed for {n:.3f} seconds\n"))
    else:
        # Delay everything
        await asyncio.sleep(n)
        response = web.Response(body=to_bytes(f"Response delayed for {n:.3f} seconds\n"))
    
    return response


async def forever_handler(request: web.Request) -> web.Response:
    """Never finish responding (for timeout tests)."""
    write = getarg(request, "write", False, type_=bool)
    
    response = web.StreamResponse()
    await response.prepare(request)
    
    if write:
        await response.write(b"some bytes")
    
    # Never finish - just wait forever
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    
    return response


async def follow_handler(request: web.Request) -> web.Response:
    """Generate links for following (with optional delay)."""
    total = getarg(request, "total", 100, type_=int)
    show = getarg(request, "show", 1, type_=int)
    order = getarg(request, "order", "desc")
    maxlatency = getarg(request, "maxlatency", 0, type_=float)
    n = getarg(request, "n", total, type_=int)
    
    # Optional random delay
    if maxlatency > 0:
        lag = random.random() * maxlatency
        await asyncio.sleep(lag)
    
    if order == "rand":
        nlist = [random.randint(1, total) for _ in range(show)]
    else:  # order == "desc"
        nlist = range(n, max(n - show, 0), -1)
    
    html = "<html><head></head><body>"
    for nl in nlist:
        # Build query string
        args = dict(request.query)
        args["n"] = str(nl)
        argstr = urlencode(args, doseq=True)
        html += f"<a href='/follow?{argstr}'>follow {nl}</a><br>"
    html += "</body></html>"
    
    return web.Response(body=html.encode(), content_type="text/html")


# Redirect Resources


async def redirect_to_handler(request: web.Request) -> web.Response:
    """Redirect to URL specified in query parameter."""
    url = getarg(request, "url", "/")
    status = getarg(request, "status", 302, type_=int)
    return web.Response(status=status, headers={"Location": url})


async def redirect_handler(request: web.Request) -> web.Response:
    """Simple redirect to /redirected."""
    return web.Response(status=302, headers={"Location": "/redirected"})


async def redirected_handler(request: web.Request) -> web.Response:
    """Target of redirect."""
    return web.Response(body=b"Redirected here", content_type="text/plain")


# Special Resources


async def compress_handler(request: web.Request) -> web.Response:
    """Return gzip-compressed response."""
    data = b"Sample data to compress" * 100
    compressed = gzip.compress(data)
    return web.Response(
        body=compressed,
        headers={
            "Content-Encoding": "gzip",
            "Content-Length": str(len(compressed)),
        }
    )


async def set_cookie_handler(request: web.Request) -> web.Response:
    """Set cookies in response.
    
    Note: This is a test mock server. Cookies intentionally lack Secure/HttpOnly
    attributes to allow testing various cookie scenarios including insecure cookies.
    """
    response = web.Response(body=b"Cookie set")
    # nosemgrep: python.flask.security.insecure-cookie.insecure-cookie
    response.set_cookie("test_cookie", "cookie_value")  # noqa: S102
    return response


async def numbers_handler(request: web.Request) -> web.Response:
    """Return large sequence of numbers."""
    numbers = [str(x).encode("utf8") for x in range(2**18)]
    return web.Response(body=b"".join(numbers), content_type="text/plain")


# Resource mapping for easy router setup
ROUTES = [
    web.get("/status", status_handler),
    web.get("/host", host_handler),
    web.post("/payload", payload_handler),
    web.post("/echo", echo_handler),
    web.get("/echo", echo_handler),
    web.get("/partial", partial_handler),
    web.get("/text", text_handler),
    web.get("/html", html_handler),
    web.get("/enc-gb18030", encoding_handler),
    web.get("/delay", delay_handler),
    web.get("/wait", forever_handler),
    web.get("/follow", follow_handler),
    web.get("/redirect-to", redirect_to_handler),
    web.get("/redirect", redirect_handler),
    web.get("/redirected", redirected_handler),
    web.get("/compress", compress_handler),
    web.get("/set-cookie", set_cookie_handler),
    web.get("/numbers", numbers_handler),
]


def create_app() -> web.Application:
    """Create aiohttp application with all routes."""
    app = web.Application()
    app.add_routes(ROUTES)
    return app
