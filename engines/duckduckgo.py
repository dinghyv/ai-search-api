import html
import re
import urllib.parse
import urllib.request

from engines.base import SearchEngine

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


class DuckDuckGoEngine(SearchEngine):
    name = "duckduckgo"
    label = "DuckDuckGo (Lite HTML)"
    description = "隐私友好的全球网页搜索，无需 API Key（海外服务器直连更佳）。"

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        data_body = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/",
            data=data_body,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            page_html = resp.read().decode("utf-8", errors="replace")

        if raw:
            return {"engine": "duckduckgo", "query": query, "html_length": len(page_html)}

        links = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            page_html,
            re.S,
        )
        snippets = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            page_html,
            re.S,
        )

        results = []
        for idx, (href, raw_title) in enumerate(links):
            if "duckduckgo.com/l/?" in href:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = qs.get("uddg", [href])[0]
            snippet = _strip_tags(snippets[idx]) if idx < len(snippets) else ""
            results.append({
                "rank": idx + 1,
                "type": "web",
                "title": _strip_tags(raw_title),
                "url": href,
                "source": urllib.parse.urlparse(href).netloc,
                "date": "",
                "snippet": snippet,
            })

        if limit > 0:
            results = results[:limit]

        return {
            "meta": {
                "engine": "duckduckgo",
                "query": query,
                "page": page,
                "pages_fetched": 1,
                "has_more": False,
                "returned_count": len(results),
                "cached": False,
            },
            "results": results,
            "hints": [],
        }
