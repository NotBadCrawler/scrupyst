# Mock 服务器迁移指南

## 概述

本指南记录了将 Scrapy 测试 mock 服务器从 Twisted 迁移到 aiohttp 的过程。
这是**第五阶段（测试迁移）的关键阻塞项**，因为所有测试都依赖这些服务器。

## 状态

**当前进度：** 基础架构已完成（约占 mock 服务器工作的 20%）

### 已完成 ✅

1. **http_base_aiohttp.py**（147 行）- 新建
   - 提供与 `BaseMockServer` 相同接口的 `BaseMockServerAiohttp` 类
   - 用于创建基于 aiohttp 的服务器运行器的 `main_factory_aiohttp()`
   - HTTP 和 HTTPS 支持，具有动态端口分配
   - 基于子进程的服务器生成（与 Twisted 版本模式相同）

2. **utils.py** - 已更新
   - 使用 Python 标准库 ssl 模块添加了 `ssl_context_factory_aiohttp()`
   - 使 Twisted 导入可选以保持向后兼容性
   - 新旧 SSL 工厂均可用

### 剩余工作 🚫

#### 高优先级：HTTP 资源（349 行）

文件 `http_resources.py` 包含测试使用的所有 Twisted web 资源。
每个资源都需要转换为 aiohttp 请求处理程序。

**转换模式：**

Twisted 资源：
```python
class Status(resource.Resource):
    isLeaf = True
    
    def render_GET(self, request):
        n = getarg(request, b"n", 200, type_=int)
        request.setResponseCode(n)
        return b""
```

Aiohttp 处理程序：
```python
async def status_handler(request):
    n = int(request.query.get('n', 200))
    return web.Response(status=n, body=b"")
```

**要转换的资源：**

1. **简单资源**（无异步延迟）：
   - `Status` - 从查询参数返回 HTTP 状态码
   - `HostHeaderResource` - 回显 Host 头
   - `PayloadResource` - 验证请求体长度
   - `Echo` - 回显请求
   - `Partial` - 部分内容响应
   - `Raw` - 原始 HTTP 响应
   - `Drop` - 断开连接
   - `Compress` - 压缩响应
   - `SetCookie` - 设置 cookie
   - `ContentLengthHeaderResource` - 自定义 Content-Length
   - `EmptyContentTypeHeaderResource` - 空 Content-Type
   - `DuplicateHeaderResource` - 重复头
   - `ResponseHeadersResource` - 自定义响应头

2. **异步资源**（使用延迟）：
   - `Follow` - 带延迟的链接跟随
   - `Delay` - 延迟响应
   - `ForeverTakingResource` - 永不完成的请求

3. **复杂资源**：
   - `BrokenDownloadResource` - 中断/损坏的下载
   - `ChunkedResource` - 分块传输编码
   - `BrokenChunkedResource` - 损坏的分块编码
   - `LargeChunkedFileResource` - 大文件块
   - `ArbitraryLengthPayloadResource` - 可变长度有效负载

4. **重定向资源**：
   - `RedirectTo` - 重定向处理程序
   - `NoMetaRefreshRedirect` - 无 meta refresh 的重定向

#### 中优先级：HTTP Mock 服务器（101 行）

文件：`http.py`

**任务：**
1. 使用 `http_base_aiohttp.py` 创建 `http_aiohttp.py`
2. 将 `Root` 资源转换为带路由的 aiohttp Application
3. 将所有资源路径映射到 aiohttp 处理程序

**转换模式：**

Twisted：
```python
class Root(resource.Resource):
    def __init__(self):
        super().__init__()
        self.putChild(b"status", Status())
        self.putChild(b"echo", Echo())
```

Aiohttp：
```python
def create_app():
    app = web.Application()
    app.router.add_get('/status', status_handler)
    app.router.add_post('/echo', echo_handler)
    return app
```

#### 中优先级：HTTPS Mock 服务器（46 行）

文件：`simple_https.py`

与 `http.py` 模式相同，但仅提供 HTTPS。完成 HTTP 版本后应该很简单。

#### 低优先级：代理回显（17 行）

文件：`proxy_echo.py`

简单的代理服务器。可能可以使用 aiohttp 的代理功能或实现简单转发。

#### 复杂：DNS Mock 服务器（67 行）

文件：`dns.py`

**挑战：** 使用 `twisted.names` DNS 服务器框架

**选项：**
1. 查找基于 asyncio 的 DNS 库（例如 `aiodns`、带 asyncio 的 `dnspython`）
2. 使用 `asyncio.DatagramProtocol` 实现简单的 DNS 服务器
3. 使用外部 DNS mock 工具（如子进程中的 `dnsmasq`）

#### 复杂：FTP Mock 服务器（59 行）

文件：`ftp.py`

**挑战：** 使用 Twisted 的 FTP 服务器

**选项：**
1. 使用 `aioftp` 库（基于 asyncio 的 FTP 服务器）
2. 使用带 asyncio 集成的 `pyftpdlib`
3. 为测试需求实现最小的 FTP 服务器

## 实施策略

### 第一阶段：核心 HTTP 资源（第 1 周）
1. 创建 `http_resources_aiohttp.py`
2. 实现所有简单资源（13 个资源）
3. 独立测试每个资源

### 第二阶段：异步 HTTP 资源（第 1-2 周）
1. 实现异步延迟资源（3 个资源）
2. 实现复杂资源（6 个资源）
3. 正确处理分块编码
4. 使用实际的 Scrapy 下载器测试

### 第三阶段：HTTP 服务器集成（第 2 周）
1. 创建 `http_aiohttp.py`
2. 将所有资源连接到路由
3. 测试完整的 HTTP mock 服务器
4. 验证所有现有测试可以使用它

### 第四阶段：HTTPS 和代理（第 2 周）
1. 实现 HTTPS 变体
2. 实现代理回显
3. 测试 SSL/TLS 功能

### 第五阶段：DNS 和 FTP（第 3-4 周）
1. 研究并选择 DNS 解决方案
2. 实现 DNS mock
3. 研究并选择 FTP 解决方案
4. 实现 FTP mock
5. 测试特殊协议处理程序

## 测试方法

对于每个转换的资源：
1. 编写独立测试比较 Twisted 和 aiohttp 版本
2. 验证相同输入的相同 HTTP 响应
3. 测试错误情况和边缘情况
4. 逐步更新依赖的测试文件

## 关键差异：Twisted vs Aiohttp

### 请求对象

Twisted：
```python
request.args[b"name"][0]  # 查询参数
request.content.read()     # 主体
request.requestHeaders.getRawHeaders(b"host")  # 头
request.setResponseCode(404)  # 设置状态
request.write(data)  # 写入响应
request.finish()  # 完成响应
```

Aiohttp：
```python
request.query.get('name')  # 查询参数
await request.read()  # 主体
request.headers.get('Host')  # 头
return web.Response(status=404)  # 设置状态
# 响应是返回的，而不是增量写入的（流式传输除外）
```

### 异步延迟

Twisted：
```python
d = deferLater(reactor, delay, function, *args)
return NOT_DONE_YET
```

Aiohttp：
```python
await asyncio.sleep(delay)
result = await function(*args)
return web.Response(...)
```

### 流式响应

Twisted：
```python
request.write(chunk1)
request.write(chunk2)
request.finish()
```

Aiohttp：
```python
response = web.StreamResponse()
await response.prepare(request)
await response.write(chunk1)
await response.write(chunk2)
await response.write_eof()
return response
```

## 创建/修改的文件

### 新文件
- `tests/mockserver/http_base_aiohttp.py` ✅
- `tests/mockserver/http_resources_aiohttp.py` (待办)
- `tests/mockserver/http_aiohttp.py` (待办)
- `tests/mockserver/simple_https_aiohttp.py` (待办)
- `tests/mockserver/dns_aiohttp.py` (待办)
- `tests/mockserver/ftp_aiohttp.py` (待办)

### 修改的文件
- `tests/mockserver/utils.py` ✅（添加了 `ssl_context_factory_aiohttp`）

### 最终要弃用的文件
- `tests/mockserver/http_base.py`
- `tests/mockserver/http_resources.py`
- `tests/mockserver/http.py`
- `tests/mockserver/simple_https.py`
- `tests/mockserver/dns.py`
- `tests/mockserver/ftp.py`

## 资源

- [aiohttp 服务器文档](https://docs.aiohttp.org/en/stable/web.html)
- [aiohttp 流式响应](https://docs.aiohttp.org/en/stable/web_quickstart.html#streaming-response)
- [aioftp 文档](https://aioftp.readthedocs.io/)
- [dnspython asyncio](https://dnspython.readthedocs.io/en/stable/async.html)

## 预估时间表

- **总工作量：** 3-4 周
- **当前进度：** ~20%（基础架构）
- **剩余：** ~80%（实现和测试）

## 下一步

1. 从 `http_resources_aiohttp.py` 中的简单 HTTP 资源开始
2. 独立测试每个资源
3. 逐步构建复杂性
4. 集成到完整的 HTTP 服务器
5. 随着 mock 服务器可用，逐步更新测试
