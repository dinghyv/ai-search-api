import asyncio
import json
import sys

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from db import get_setting, init_db
from engines import get_engine, list_engines

init_db()

mcp = MCPServer(
    "ai-search-api",
    instructions="提供多引擎实时网页搜索能力（默认腾讯元宝搜索 so_qq，支持切换 Brave / DuckDuckGo）。",
)


@mcp.tool()
async def web_search(
    query: str,
    page: int = 1,
    limit: int = 10,
    engine: str = "",
    include_ai: bool = True,
    include_media: bool = False,
) -> str:
    """搜索互联网网页、公众号文章与资讯，返回结构化 JSON 结果。

    Args:
        query: 搜索关键词（如 "DeepSeek 大肥鱼"、"Python FastAPI 教程"）
        page: 起始页码，默认 1
        limit: 期望返回的结果条数（默认 10；设大如 20~30 会自动翻页聚合；0 表示当前页全部）
        engine: 搜索引擎标识（留空则使用控制台默认引擎，可选 so_qq / brave / duckduckgo）
        include_ai: 是否包含 AI 概览与权威溯源引用，默认 True
        include_media: 是否包含图片与视频扩展字段，默认 False（节省上下文 Token）
    """
    chosen = (engine or get_setting("default_engine", "so_qq")).strip()
    eng = get_engine(chosen)
    data = await asyncio.to_thread(
        eng.search,
        query=query.strip(),
        page=max(1, page),
        limit=max(0, min(limit, 60)),
        include_ai=include_ai,
        include_media=include_media,
        raw=False,
    )
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_search_engines() -> str:
    """列出当前已注册的搜索引擎及其配置说明。"""
    return json.dumps(
        {
            "default_engine": get_setting("default_engine", "so_qq"),
            "engines": list_engines(),
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
