import base64
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
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\u2002", " ").strip()


def _decode_bing_url(href: str) -> str:
    if "bing.com/ck/a" not in href:
        return href
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        u = qs.get("u", [""])[0]
        if u.startswith("a1"):
            b64 = u[2:]
            b64 += "=" * (-len(b64) % 4)
            return base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
    except Exception:
        pass
    return href


class BingEngine(SearchEngine):
    name = "bing"
    label = "必应搜索 (cn.bing.com)"
    description = "中英文高质量网页搜索，免密钥直连，支持翻页 (&first=)。"

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
            params["first"] = str((page - 1) * 10 + 1)
        url = "https://cn.bing.com/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            page_html = resp.read().decode("utf-8", errors="replace")

        if raw:
            return {"engine": "bing", "query": query, "page": page, "html_length": len(page_html)}

        items = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', page_html, re.S)
        results = []
        for item_html in items:
            h2_m = re.search(r"<h2[^>]*>\s*<a\b([^>]*)>(.*?)</a>\s*</h2>", item_html, re.S)
            if not h2_m:
                continue
            attrs, raw_title = h2_m.group(1), h2_m.group(2)
            href_m = re.search(r'href="([^"]+)"', attrs)
            if not href_m:
                continue
            target_url = _decode_bing_url(html.unescape(href_m.group(1)))

            src_m = re.search(r'<div class="tptt"[^>]*>(.*?)</div>', item_html, re.S)
            source = _strip_tags(src_m.group(1)) if src_m else urllib.parse.urlparse(target_url).netloc

            p_m = re.search(r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', item_html, re.S)
            snippet = _strip_tags(p_m.group(1)) if p_m else ""

            results.append({
                "rank": len(results) + 1,
                "type": "web",
                "title": _strip_tags(raw_title),
                "url": target_url,
                "source": source,
                "date": "",
                "snippet": snippet,
            })

        if limit > 0:
            results = results[:limit]

        return {
            "meta": {
                "engine": "bing",
                "query": query,
                "page": page,
                "pages_fetched": 1,
                "has_more": len(results) >= 8,
                "returned_count": len(results),
                "cached": False,
            },
            "results": results,
            "hints": [],
        }
