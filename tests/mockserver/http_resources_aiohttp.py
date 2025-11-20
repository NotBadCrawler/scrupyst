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


# Complex Resources (Edge cases, broken transfers, etc.)


async def raw_handler(request: web.Request) -> web.Response:
    """Return raw HTTP response (for testing malformed responses)."""
    raw = getarg(request, "raw", "HTTP/1.1 200 OK\n", type_=str)
    
    # Use StreamResponse to send raw bytes
    response = web.StreamResponse()
    response.force_close()
    await response.prepare(request)
    await response.write(to_bytes(raw))
    
    # Close connection after sending raw data
    await response.write_eof()
    return response


async def drop_handler(request: web.Request) -> web.Response:
    """Drop connection after writing some data."""
    abort = getarg(request, "abort", 0, type_=int)
    
    response = web.StreamResponse()
    response.force_close()
    await response.prepare(request)
    await response.write(b"this connection will be dropped\n")
    
    # Force close the connection
    if abort:
        # Simulate abrupt connection termination
        await response.write_eof()
    else:
        # Normal close
        await response.write_eof()
    
    return response


async def arbitrary_length_payload_handler(request: web.Request) -> web.Response:
    """Echo request body back (arbitrary length)."""
    data = await request.read()
    return web.Response(body=data)


async def no_meta_refresh_redirect_handler(request: web.Request) -> web.Response:
    """Redirect without meta-refresh tag."""
    # Standard redirect without meta refresh
    return web.Response(
        status=302,
        headers={"Location": "/redirected"},
        body=b'<html><head></head><body>Moved</body></html>',
        content_type="text/html"
    )


async def content_length_header_handler(request: web.Request) -> web.Response:
    """Echo the Content-Length header value."""
    content_length = request.headers.get("Content-Length", "0")
    return web.Response(body=content_length.encode())


async def chunked_handler(request: web.Request) -> web.Response:
    """Return chunked transfer encoding response."""
    response = web.StreamResponse()
    response.enable_chunked_encoding()
    await response.prepare(request)
    
    # Send data in chunks with a small delay
    await asyncio.sleep(0)
    await response.write(b"chunked ")
    await response.write(b"content\n")
    
    await response.write_eof()
    return response


async def broken_chunked_handler(request: web.Request) -> web.Response:
    """Return broken chunked transfer (incomplete)."""
    response = web.StreamResponse()
    response.enable_chunked_encoding()
    await response.prepare(request)
    
    # Send some chunked data
    await response.write(b"chunked ")
    await response.write(b"content\n")
    
    # Don't send terminating chunk - just close connection
    response.force_close()
    # Note: In aiohttp, we can't easily break chunking, so we just force close
    return response


async def broken_download_handler(request: web.Request) -> web.Response:
    """Return incomplete response (Content-Length mismatch)."""
    response = web.StreamResponse()
    response.headers["Content-Length"] = "20"
    await response.prepare(request)
    
    # Send less data than promised
    await asyncio.sleep(0)
    await response.write(b"partial")  # Only 7 bytes, not 20
    
    # Force close connection without sending full content
    response.force_close()
    return response


async def empty_content_type_handler(request: web.Request) -> web.Response:
    """Echo request body without Content-Type header."""
    data = await request.read()
    response = web.Response(body=data)
    # Set empty content-type
    response.headers["Content-Type"] = ""
    return response


async def large_chunked_file_handler(request: web.Request) -> web.Response:
    """Return large file in chunks (1MB)."""
    response = web.StreamResponse()
    response.enable_chunked_encoding()
    await response.prepare(request)
    
    # Send 1MB in 1KB chunks
    for i in range(1024):
        await response.write(b"x" * 1024)
    
    await response.write_eof()
    return response


async def duplicate_header_handler(request: web.Request) -> web.Response:
    """Return response with duplicate Set-Cookie headers."""
    response = web.Response(body=b"")
    # nosemgrep: python.flask.security.insecure-cookie.insecure-cookie
    response.headers.add("Set-Cookie", "a=b")  # noqa: S102
    # nosemgrep: python.flask.security.insecure-cookie.insecure-cookie
    response.headers.add("Set-Cookie", "c=d")  # noqa: S102
    return response


async def uri_handler(request: web.Request) -> web.Response:
    """Echo the full request URI."""
    # Note: For CONNECT requests (used in proxy tests), return empty
    if request.method == "CONNECT":
        return web.Response(body=b"")
    
    # Return full URI path + query string
    uri = request.path_qs
    return web.Response(body=uri.encode())


async def response_headers_handler(request: web.Request) -> web.Response:
    """Set response headers from JSON request body."""
    data = await request.read()
    body = json.loads(data.decode())
    
    headers = {}
    for header_name, header_value in body.items():
        headers[header_name] = header_value
    
    return web.Response(body=json.dumps(body).encode("utf-8"), headers=headers)


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
    # Complex/edge case handlers
    web.get("/raw", raw_handler),
    web.post("/raw", raw_handler),
    web.get("/drop", drop_handler),
    web.post("/alpayload", arbitrary_length_payload_handler),
    web.get("/redirect-no-meta-refresh", no_meta_refresh_redirect_handler),
    web.get("/contentlength", content_length_header_handler),
    web.get("/chunked", chunked_handler),
    web.get("/broken-chunked", broken_chunked_handler),
    web.get("/broken", broken_download_handler),
    web.get("/nocontenttype", empty_content_type_handler),
    web.post("/nocontenttype", empty_content_type_handler),
    web.get("/largechunkedfile", large_chunked_file_handler),
    web.get("/duplicate-header", duplicate_header_handler),
    web.get("/uri", uri_handler),
    web.post("/uri", uri_handler),
    web.post("/response-headers", response_headers_handler),
]


def create_app() -> web.Application:
    """Create aiohttp application with all routes."""
    app = web.Application()
    app.add_routes(ROUTES)
    return app
