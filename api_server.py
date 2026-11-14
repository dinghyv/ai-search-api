import asyncio
from contextlib import asynccontextmanager
import os
import sys

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from admin_ui import router as admin_router
import db
from engines import get_engine, list_engines
from mcp_server import mcp

db.init_db()

mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    host=os.environ.get("HOST", "0.0.0.0"),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="AI Search API + MCP (Multi-Engine)",
    description=(
        "多引擎聚合搜索 API 与远程 MCP 服务（默认腾讯元宝搜索 so_qq，支持扩展 Brave / DuckDuckGo / 百度等），"
        "内置 SQLite 控制台管理 API Key 与引擎设置。"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    path = request.url.path
    # 控制台、健康检查与文档无需 API Key
    if (
        path == "/"
        or path.startswith("/admin")
        or path in ("/health", "/docs", "/openapi.json", "/redoc")
    ):
        return await call_next(request)

    require_key = db.get_setting("require_api_key", "1") == "1"
    token = ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = request.headers.get("x-api-key", "").strip()
    if not token:
        token = request.query_params.get("api_key", "").strip()

    key_name = db.verify_api_key(token) if token else None
    if require_key and not key_name:
        return JSONResponse(
            {"detail": "Invalid or missing API Key. Pass Authorization: Bearer <sk-...>"},
            status_code=401,
        )

    request.state.api_key_name = key_name or "anonymous"
    return await call_next(request)


app.include_router(admin_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/admin")


@app.get("/health", summary="健康检查")
async def health():
    return {"status": "ok"}


@app.get("/v1/engines", summary="列出可用搜索引擎")
async def get_engines():
    return {
        "default_engine": db.get_setting("default_engine", "so_qq"),
        "engines": list_engines(),
    }


async def _handle_search(
    request: Request,
    q: str,
    page: int,
    limit: int,
    engine: str | None,
    include_ai: bool,
    include_media: bool,
    raw: bool,
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter 'q' cannot be empty.")

    chosen_engine = (engine or db.get_setting("default_engine", "so_qq")).strip()
    try:
        eng = get_engine(chosen_engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = await asyncio.to_thread(
            eng.search,
            query=query,
            page=page,
            limit=limit,
            include_ai=include_ai,
            include_media=include_media,
            raw=raw,
        )
        key_name = getattr(request.state, "api_key_name", None)
        db.log_search(key_name, eng.name, query, page)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream search failed: {exc}") from exc


@app.get(
    "/v1/search",
    summary="执行多引擎网页搜索",
    description="搜索关键词并返回统一结构化 JSON，支持切换 engine、page 翻页及 limit 自动跨页聚合。",
)
async def search_v1(
    request: Request,
    q: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="起始页码，从 1 开始"),
    limit: int = Query(
        10,
        ge=0,
        le=60,
        description="期望返回的结果条数（0 表示仅返回当前页全部结果；大于单页条数时自动向后翻页聚合）",
    ),
    engine: str | None = Query(None, description="搜索引擎标识（默认使用控制台配置，如 so_qq / brave / duckduckgo）"),
    include_ai: bool = Query(True, description="是否包含 AI 概览与权威溯源列表"),
    include_media: bool = Query(True, description="是否包含图片与视频扩展字段"),
    raw: bool = Query(False, description="调试开关：返回原始数据"),
):
    return await _handle_search(request, q, page, limit, engine, include_ai, include_media, raw)


@app.get("/search", include_in_schema=False)
async def search_compat(
    request: Request,
    q: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(0, ge=0, le=60),
    engine: str | None = Query(None),
    include_ai: bool = Query(True),
    include_media: bool = Query(True),
    raw: bool = Query(False),
):
    return await _handle_search(request, q, page, limit, engine, include_ai, include_media, raw)


# 挂载远程 MCP Streamable HTTP 端点（访问路径：/mcp/）
app.mount("/mcp", mcp_http_app)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8787"))
    uvicorn.run(app, host=host, port=port)
