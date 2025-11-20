# Mock Server Migration Guide

## Overview

This guide documents the migration of Scrapy's test mock servers from Twisted to aiohttp.
This is a **critical blocker** for Phase 5 (test migration) as all tests depend on these servers.

## Status

**Current Progress:** Infrastructure foundation complete (~20% of mock server work)

### Completed ✅

1. **http_base_aiohttp.py** (147 lines) - NEW
   - `BaseMockServerAiohttp` class providing same interface as `BaseMockServer`
   - `main_factory_aiohttp()` for creating aiohttp-based server runners
   - HTTP and HTTPS support with dynamic port allocation
   - Subprocess-based server spawning (same pattern as Twisted version)

2. **utils.py** - UPDATED
   - Added `ssl_context_factory_aiohttp()` using Python's stdlib ssl module
   - Made Twisted imports optional for backward compatibility
   - Both old and new SSL factories available

### Remaining Work 🚫

#### High Priority: HTTP Resources (349 lines)

The file `http_resources.py` contains all the Twisted web resources used by tests.
Each resource needs to be converted to an aiohttp request handler.

**Conversion Pattern:**

Twisted Resource:
```python
class Status(resource.Resource):
    isLeaf = True
    
    def render_GET(self, request):
        n = getarg(request, b"n", 200, type_=int)
        request.setResponseCode(n)
        return b""
```

Aiohttp Handler:
```python
async def status_handler(request):
    n = int(request.query.get('n', 200))
    return web.Response(status=n, body=b"")
```

**Resources to Convert:**

1. **Simple Resources** (no async delays):
   - `Status` - Return HTTP status code from query param
   - `HostHeaderResource` - Echo Host header
   - `PayloadResource` - Validate request body length
   - `Echo` - Echo request back
   - `Partial` - Partial content responses
   - `Raw` - Raw HTTP response
   - `Drop` - Drop connection
   - `Compress` - Compressed responses
   - `SetCookie` - Set cookies
   - `ContentLengthHeaderResource` - Custom Content-Length
   - `EmptyContentTypeHeaderResource` - Empty Content-Type
   - `DuplicateHeaderResource` - Duplicate headers
   - `ResponseHeadersResource` - Custom response headers

2. **Async Resources** (use delays):
   - `Follow` - Link following with delays
   - `Delay` - Delayed responses
   - `ForeverTakingResource` - Never-finishing requests

3. **Complex Resources**:
   - `BrokenDownloadResource` - Broken/interrupted downloads
   - `ChunkedResource` - Chunked transfer encoding
   - `BrokenChunkedResource` - Broken chunked encoding
   - `LargeChunkedFileResource` - Large file chunks
   - `ArbitraryLengthPayloadResource` - Variable-length payloads

4. **Redirect Resources**:
   - `RedirectTo` - Redirect handler
   - `NoMetaRefreshRedirect` - Redirect without meta refresh

#### Medium Priority: HTTP Mock Server (101 lines)

File: `http.py`

**Tasks:**
1. Create `http_aiohttp.py` using `http_base_aiohttp.py`
2. Convert `Root` resource to aiohttp Application with routes
3. Map all resource paths to aiohttp handlers

**Conversion Pattern:**

Twisted:
```python
class Root(resource.Resource):
    def __init__(self):
        super().__init__()
        self.putChild(b"status", Status())
        self.putChild(b"echo", Echo())
```

Aiohttp:
```python
def create_app():
    app = web.Application()
    app.router.add_get('/status', status_handler)
    app.router.add_post('/echo', echo_handler)
    return app
```

#### Medium Priority: HTTPS Mock Server (46 lines)

File: `simple_https.py`

Same pattern as `http.py` but only serves HTTPS. Should be straightforward once HTTP version is done.

#### Low Priority: Proxy Echo (17 lines)

File: `proxy_echo.py`

Simple proxy server. Can likely use aiohttp's proxy capabilities or implement simple forwarding.

#### Complex: DNS Mock Server (67 lines)

File: `dns.py`

**Challenge:** Uses `twisted.names` DNS server framework

**Options:**
1. Find asyncio-based DNS library (e.g., `aiodns`, `dnspython` with asyncio)
2. Implement simple DNS server with `asyncio.DatagramProtocol`
3. Use external DNS mock tool (like `dnsmasq` in subprocess)

#### Complex: FTP Mock Server (59 lines)

File: `ftp.py`

**Challenge:** Uses Twisted's FTP server

**Options:**
1. Use `aioftp` library (asyncio-based FTP server)
2. Use `pyftpdlib` with asyncio integration
3. Implement minimal FTP server for test needs

## Implementation Strategy

### Phase 1: Core HTTP Resources (Week 1)
1. Create `http_resources_aiohttp.py`
2. Implement all simple resources (13 resources)
3. Test each resource independently

### Phase 2: Async HTTP Resources (Week 1-2)
1. Implement async delay resources (3 resources)
2. Implement complex resources (6 resources)
3. Handle chunked encoding properly
4. Test with actual Scrapy downloader

### Phase 3: HTTP Server Integration (Week 2)
1. Create `http_aiohttp.py`
2. Wire up all resources to routes
3. Test full HTTP mock server
4. Verify all existing tests can use it

### Phase 4: HTTPS & Proxy (Week 2)
1. Implement HTTPS variant
2. Implement proxy echo
3. Test SSL/TLS functionality

### Phase 5: DNS & FTP (Week 3-4)
1. Research and choose DNS solution
2. Implement DNS mock
3. Research and choose FTP solution
4. Implement FTP mock
5. Test specialty protocol handlers

## Testing Approach

For each converted resource:
1. Write standalone test comparing Twisted and aiohttp versions
2. Verify same HTTP responses for same inputs
3. Test error cases and edge cases
4. Update dependent test files incrementally

## Key Differences: Twisted vs Aiohttp

### Request Object

Twisted:
```python
request.args[b"name"][0]  # Query params
request.content.read()     # Body
request.requestHeaders.getRawHeaders(b"host")  # Headers
request.setResponseCode(404)  # Set status
request.write(data)  # Write response
request.finish()  # Complete response
```

Aiohttp:
```python
request.query.get('name')  # Query params
await request.read()  # Body
request.headers.get('Host')  # Headers
return web.Response(status=404)  # Set status
# Response is returned, not written incrementally (except streaming)
```

### Async Delays

Twisted:
```python
d = deferLater(reactor, delay, function, *args)
return NOT_DONE_YET
```

Aiohttp:
```python
await asyncio.sleep(delay)
result = await function(*args)
return web.Response(...)
```

### Streaming Responses

Twisted:
```python
request.write(chunk1)
request.write(chunk2)
request.finish()
```

Aiohttp:
```python
response = web.StreamResponse()
await response.prepare(request)
await response.write(chunk1)
await response.write(chunk2)
await response.write_eof()
return response
```

## Files Created/Modified

### New Files
- `tests/mockserver/http_base_aiohttp.py` ✅
- `tests/mockserver/http_resources_aiohttp.py` (TODO)
- `tests/mockserver/http_aiohttp.py` (TODO)
- `tests/mockserver/simple_https_aiohttp.py` (TODO)
- `tests/mockserver/dns_aiohttp.py` (TODO)
- `tests/mockserver/ftp_aiohttp.py` (TODO)

### Modified Files
- `tests/mockserver/utils.py` ✅ (added `ssl_context_factory_aiohttp`)

### Files to Deprecate (Eventually)
- `tests/mockserver/http_base.py`
- `tests/mockserver/http_resources.py`
- `tests/mockserver/http.py`
- `tests/mockserver/simple_https.py`
- `tests/mockserver/dns.py`
- `tests/mockserver/ftp.py`

## Resources

- [aiohttp Server Documentation](https://docs.aiohttp.org/en/stable/web.html)
- [aiohttp Streaming Response](https://docs.aiohttp.org/en/stable/web_quickstart.html#streaming-response)
- [aioftp Documentation](https://aioftp.readthedocs.io/)
- [dnspython asyncio](https://dnspython.readthedocs.io/en/stable/async.html)

## Estimated Timeline

- **Total Effort:** 3-4 weeks
- **Current Progress:** ~20% (infrastructure)
- **Remaining:** ~80% (implementation & testing)

## Next Steps

1. Start with simple HTTP resources in `http_resources_aiohttp.py`
2. Test each resource independently
3. Build up complexity gradually
4. Integrate into full HTTP server
5. Update tests incrementally as mock servers become available
