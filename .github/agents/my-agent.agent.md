---
# Fill in the fields below to create a basic custom agent for your repository.
# The Copilot CLI can be used for local testing: https://gh.io/customagents/cli
# To make this agent available, merge this file into the default repository branch.
# For format details, see: https://gh.io/customagents/config

name: 通用 AGENT
description:
---

## [通用项目标准]
### 语言
主要语言是简体中文 (除了文件名, 无论是生成指令、代码、注释还是 git 的评论和 PR, 都用简体中文生成内容);

### 依赖
无论是依赖还是工具, 尽可能用最新版, 尽可能用非中国大陆的开发者或公司开发的;

## [Python 项目编码标准]
### 工具偏好
    - 依赖相关的一律使用 uv, 比如 uv add;
    - 运行 python 程序一律使用 uv run python <file>;
    - python版本一律使用 3.13 以上的版本;
    - 一律使用异步编程(asyncio);
    - 格式化代码用 ruff format;
    - 静态代码检查用 ruff check, 在pycharm.toml里启用 ALL 规则, 忽略 D211, D213 规则;
    - 类型检查用 pylance-mcp;

### 依赖偏好 (用最新版)
    - 网络请求优先用 aiohttp;
    - 自动化优先用 playwright(测试的时候用有头模式);
    - 后端服务优先用 fastapi;
    - 日志优先用 loguru;
    - 文件操作优先用 aiofiles;
    - 配置文件优先用 pydantic;
    - 数据库操作优先用 sqlmodel;
    - 测试优先用 pytest-asyncio;
    - 数据处理优先用 polars;
    - 环境变量优先用 python-dotenv;
    - 任务调度优先用 apscheduler;
    - 命令行优先用 typer;
    - json 优先用 orjson;

### 代码风格
    完全采用 ruff 的 ALL 规则, 要足够 pythonic, 尽可能使用 python 新版本的语法和功能;
