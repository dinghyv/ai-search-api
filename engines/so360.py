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


class So360Engine(SearchEngine):
    name = "so360"
    label = "360 搜索 (so.com)"
    description = "中文网页搜索，免密钥直连，支持翻页 (&pn=)。"

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        params = {"q": query}
        if page > 1:
            params["pn"] = str(page)
        url = "https://www.so.com/s?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            page_html = resp.read().decode("utf-8", errors="replace")

        if raw:
            return {"engine": "so360", "query": query, "page": page, "html_length": len(page_html)}

        items = re.findall(r'<li[^>]*class="[^"]*res-list[^"]*"[^>]*>(.*?)</li>', page_html, re.S)
        results = []
        for item_html in items:
            title_m = re.search(
                r'<h3[^>]*class="[^"]*res-title[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>',
                item_html,
                re.S,
            )
            if not title_m:
                continue
            a_tag_m = re.search(r"<a\b([^>]*)>", item_html, re.S)
            a_attrs = a_tag_m.group(1) if a_tag_m else ""
            mdurl_m = re.search(r'data-mdurl="([^"]+)"', a_attrs)
            href_m = re.search(r'href="([^"]+)"', a_attrs)
            target_url = html.unescape(mdurl_m.group(1) if mdurl_m else (href_m.group(1) if href_m else ""))
            if not target_url:
                continue

            desc_m = re.search(
                r'<p[^>]*class="[^"]*res-desc[^"]*"[^>]*>(.*?)</p>',
                item_html,
                re.S,
            )
            snippet = _strip_tags(desc_m.group(1)) if desc_m else ""

            results.append({
                "rank": len(results) + 1,
                "type": "web",
                "title": _strip_tags(title_m.group(1)),
                "url": target_url,
                "source": urllib.parse.urlparse(target_url).netloc,
                "date": "",
                "snippet": snippet,
            })

        if limit > 0:
            results = results[:limit]

        return {
            "meta": {
                "engine": "so360",
                "query": query,
                "page": page,
                "pages_fetched": 1,
                "has_more": len(results) > 0,
                "returned_count": len(results),
                "cached": False,
            },
            "results": results,
            "hints": [],
        }
