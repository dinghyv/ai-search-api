import base64
import html
import http.cookiejar
import re
import threading
import urllib.parse
import urllib.request

from engines.base import SearchEngine

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_COOKIE_LOCK = threading.Lock()
_OPENER: urllib.request.OpenerDirector | None = None


def _get_opener(reset: bool = False) -> urllib.request.OpenerDirector:
    global _OPENER
    with _COOKIE_LOCK:
        if _OPENER is None or reset:
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            opener.addheaders = [
                ("User-Agent", UA),
                (
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                ),
                ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
                ("Referer", "https://cn.bing.com/"),
                ("Sec-Fetch-Dest", "document"),
                ("Sec-Fetch-Mode", "navigate"),
                ("Sec-Fetch-Site", "same-origin"),
            ]
            try:
                opener.open("https://cn.bing.com/", timeout=8).read(1024)
            except Exception:
                pass
            _OPENER = opener
        return _OPENER


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


def _looks_poisoned(query: str, results: list[dict]) -> bool:
    """检测 Bing 机房 IP 软风控返回的无关兜底页（如全页 Microsoft/WPS）。"""
    if len(results) < 3:
        return False
    tokens = [t.lower() for t in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", query)]
    if not tokens:
        tokens = [c.lower() for c in query if not c.isspace()]
    if not tokens:
        return False
    for r in results[:5]:
        hay = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}".lower()
        if any(tok in hay for tok in tokens):
            return False
    return True


def _fetch_bing_html(query: str, page: int, reset_cookie: bool = False) -> str:
    params = {"q": query, "ensearch": "0"}
    if page > 1:
        params["first"] = str((page - 1) * 10 + 1)
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(params)
    opener = _get_opener(reset=reset_cookie)
    with opener.open(url, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_bing_html(page_html: str) -> list[dict]:
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
    return results


class BingEngine(SearchEngine):
    name = "bing"
    label = "必应搜索 (cn.bing.com)"
    description = "中英文高质量网页搜索，带会话 Cookie 与软风控检测，支持翻页。"

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        page_html = _fetch_bing_html(query, page, reset_cookie=False)
        if raw:
            return {"engine": "bing", "query": query, "page": page, "html_length": len(page_html)}

        results = _parse_bing_html(page_html)
        if _looks_poisoned(query, results):
            page_html = _fetch_bing_html(query, page, reset_cookie=True)
            results = _parse_bing_html(page_html)
            if _looks_poisoned(query, results):
                raise RuntimeError("Bing 返回无关兜底页（机房 IP 软风控），请改用 so_qq 或 so360")

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
