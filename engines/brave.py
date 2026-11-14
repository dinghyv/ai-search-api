import gzip
import json
import urllib.parse
import urllib.request

from db import get_setting
from engines.base import SearchEngine


class BraveEngine(SearchEngine):
    name = "brave"
    label = "Brave Search API"
    description = "英文/全球高质量网页搜索，需在控制台配置 brave_api_key。"
    config_key = "brave_api_key"

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        token = get_setting("brave_api_key", "").strip()
        if not token:
            raise RuntimeError("Brave API Key 未配置，请在管理控制台 -> 引擎设置 中填写 brave_api_key。")

        count = min(max(limit or 10, 1), 20)
        offset = max(page - 1, 0)
        params = urllib.parse.urlencode({"q": query, "count": count, "offset": offset})
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": token,
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_bytes = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw_bytes = gzip.decompress(raw_bytes)
            data = json.loads(raw_bytes.decode("utf-8", errors="replace"))

        if raw:
            return {"engine": "brave", "query": query, "page": page, "raw": data}

        web_results = data.get("web", {}).get("results", [])
        results = []
        for i, item in enumerate(web_results, start=1):
            results.append({
                "rank": i,
                "type": "web",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("profile", {}).get("name") or item.get("meta_url", {}).get("hostname", ""),
                "date": item.get("page_age", ""),
                "snippet": item.get("description", ""),
            })

        return {
            "meta": {
                "engine": "brave",
                "query": query,
                "page": page,
                "pages_fetched": 1,
                "has_more": len(web_results) >= count,
                "returned_count": len(results),
                "cached": False,
            },
            "results": results,
            "hints": [],
        }
