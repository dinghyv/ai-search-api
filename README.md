# AI Search API + MCP (so.qq.com)

基于腾讯元宝搜索 (`https://so.qq.com/isearch`) RSC 协议的轻量级本地搜索服务，同时提供 **FastAPI REST API** 与 **MCP Server**，方便各类 AI Agent / IDE / 工作流直接调用。

## 目录结构

- `so.py`：核心搜索与 RSC Flight 解析引擎（支持 `page` 翻页、`limit` 自动跨页聚合、5 分钟 TTL 缓存、图文视频扩展字段）
- `api_server.py`：FastAPI 服务（提供 `/v1/search`、`/search` 兼容路由、`/docs` 与 `/openapi.json`）
- `mcp_server.py`：MCP Server（暴露 `web_search` 工具，支持 `stdio` 和 `--http` 模式）
- `requirements.txt`：项目依赖

## 安装依赖（推荐使用虚拟环境）

```powershell
cd F:\MyProgrammes\ai-search-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 1. 启动统一服务（同时提供 REST API + 远程 MCP）

```powershell
.\.venv\Scripts\python.exe api_server.py 8787
```

默认监听 `0.0.0.0:8787`（支持环境变量 `HOST`、`PORT`，以及可选鉴权 `API_KEY`）：
- 搜索接口：`http://<服务器IP>:8787/v1/search?q=大肥鱼&page=1&limit=15`
- 远程 MCP 端点（Streamable HTTP）：`http://<服务器IP>:8787/mcp/`
- Swagger / OpenAPI：`http://<服务器IP>:8787/docs`、`http://<服务器IP>:8787/openapi.json`

### Docker 一键部署

```bash
docker build -t ai-search-api .
docker run -d --name ai-search-api -p 8787:8787 -e API_KEY=your_secret_key ai-search-api
```

## 2. 接入 MCP

### 方式 A：远程服务器 HTTP 模式（推荐用于服务器部署）

在支持 Streamable HTTP 的 MCP 客户端（如 Cursor / Antigravity / Dify / 各类 Agent 框架）中配置：

```json
{
  "mcpServers": {
    "ai-search": {
      "url": "https://your-domain.com/mcp/",
      "headers": {
        "Authorization": "Bearer your_secret_key"
      }
    }
  }
}
```

### 方式 B：本地 stdio 模式

在客户端的 `mcpServers` 配置中添加：

```json
{
  "mcpServers": {
    "ai-search": {
      "command": "F:\\MyProgrammes\\ai-search-api\\.venv\\Scripts\\python.exe",
      "args": ["F:\\MyProgrammes\\ai-search-api\\mcp_server.py"]
    }
  }
}
```

如需以 HTTP 方式启动 MCP：

```powershell
.\.venv\Scripts\python.exe mcp_server.py --http
```
