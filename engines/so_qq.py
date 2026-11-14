import json
import re
import threading
import time
import urllib.parse
import urllib.request

from engines.base import SearchEngine

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CACHE_TTL = 300
MAX_AUTO_PAGES = 5
_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def clean_text(text: str, keep_citations: bool = False) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\ue40a\ue40b]", "", text)
    text = re.sub(r"</?em>", "", text)
    if keep_citations:
        text = re.sub(r"\ue417(.*?)\ue418", r"[\1]", text)
    else:
        text = re.sub(r"\ue417.*?\ue418", "", text)
    return text.strip()


def _parse_rsc_flight(raw: bytes) -> dict:
    pos, n, records = 0, len(raw), {}
    while pos < n:
        colon = raw.find(b":", pos)
        if colon == -1:
            break
        rid = raw[pos:colon].decode("utf-8", errors="replace")
        rest = colon + 1
        if rest < n and raw[rest : rest + 1] == b"T":
            comma = raw.find(b",", rest + 1)
            hlen = int(raw[rest + 1 : comma].decode("ascii"), 16)
            start = comma + 1
            end = start + hlen
            records[rid] = ("T", raw[start:end].decode("utf-8", errors="replace"))
            pos = end
        else:
            nl = raw.find(b"\n", rest)
            if nl == -1:
                nl = n
            records[rid] = ("L", raw[rest:nl].decode("utf-8", errors="replace"))
            pos = nl + 1
    return records


def _resolve_refs(obj, records: dict):
    if isinstance(obj, str) and obj.startswith("$") and obj[1:] in records:
        kind, payload = records[obj[1:]]
        if kind == "T":
            s = payload.lstrip()
            if s.startswith("{") or s.startswith("["):
                try:
                    return _resolve_refs(json.loads(payload), records)
                except Exception:
                    return payload
            return payload
    elif isinstance(obj, list):
        return [_resolve_refs(x, records) for x in obj]
    elif isinstance(obj, dict):
        return {k: _resolve_refs(v, records) for k, v in obj.items()}
    return obj


def _find_first_text(obj, keys: tuple[str, ...]) -> str:
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                val = obj[k]
                if isinstance(val, str) and val.strip():
                    return val
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    txt = val[0].get("#text")
                    if isinstance(txt, str) and txt.strip():
                        return txt
        for v in obj.values():
            found = _find_first_text(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_first_text(item, keys)
            if found:
                return found
    return ""


def _fetch_cards_props(query: str, page: int) -> tuple[dict, bool]:
    cache_key = (query, page)
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1], True

    params = {"query": query}
    if page > 1:
        params["page"] = str(page)
    url = "https://so.qq.com/isearch?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "RSC": "1"})
    raw = urllib.request.urlopen(req, timeout=15).read()
    records = _parse_rsc_flight(raw)

    cards_props = {}
    for kind, payload in records.values():
        if kind == "L" and "initialCards" in payload:
            tree = _resolve_refs(json.loads(payload), records)
            cards_props = tree[1][3]
            break

    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, cards_props)
    return cards_props, False


def _compact_dict(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _extract_page(cards_props: dict, start_rank: int = 1) -> dict:
    cards = cards_props.get("initialCards", [])
    results, hints, ai_sources, follow_ups, images, videos = [], [], [], [], [], []
    ai_answer = ""

    for card in cards:
        data = card.get("data", {})
        cname = data.get("cardName", "")
        vm = data.get("vm", {})
        if not isinstance(vm, dict):
            continue

        if cname.endswith("card_ai_overview"):
            if not ai_answer:
                raw_ans = _find_first_text(vm, ("full_answer", "longanswer"))
                ai_answer = clean_text(raw_ans, keep_citations=True)
            for sup in vm.get("supList", []):
                pf = sup.get("passage_feature", {})
                ai_sources.append({
                    "index": sup.get("sup_num"),
                    "title": clean_text(sup.get("sup_title", "")),
                    "url": sup.get("sup_url", ""),
                    "source": clean_text(sup.get("sup_source", "")),
                    "date": pf.get("doc_timestr", "") or sup.get("update_time", ""),
                    "authority": pf.get("confidence_str", ""),
                })
            for eq in vm.get("extendQueries", []):
                if isinstance(eq, str) and eq.strip():
                    follow_ups.append(clean_text(eq))
                elif isinstance(eq, dict):
                    q_txt = clean_text(eq.get("query") or eq.get("text") or "")
                    if q_txt:
                        follow_ups.append(q_txt)

        elif cname.endswith(("card_normal_result", "card30010588")):
            sublinks = []
            for sl in vm.get("sublinks") or []:
                if isinstance(sl, dict) and sl.get("url"):
                    sublinks.append({
                        "title": clean_text(sl.get("title", "")),
                        "url": sl.get("url", ""),
                    })
            extra = _compact_dict({
                "host": vm.get("host", ""),
                "image_url": vm.get("imageUrl", ""),
                "original_url": vm.get("originalUrl", ""),
                "tags": vm.get("tags") or [],
                "sublinks": sublinks,
            })
            item = {
                "rank": start_rank + len(results),
                "type": "web",
                "title": clean_text(vm.get("title", "")),
                "url": vm.get("url", ""),
                "source": vm.get("sourcename") or vm.get("host", ""),
                "date": vm.get("date", ""),
                "snippet": clean_text(vm.get("content", "")),
            }
            if extra:
                item["extra"] = extra
            results.append(item)

        elif cname.endswith("card30010608"):
            extra = _compact_dict({
                "author": vm.get("author", ""),
                "cover": vm.get("cover", ""),
                "view_num": vm.get("viewNum"),
                "like_num": vm.get("likeNum"),
                "comment_num": vm.get("comNum"),
            })
            item = {
                "rank": start_rank + len(results),
                "type": vm.get("showname", "article"),
                "title": clean_text(vm.get("title", "")),
                "url": vm.get("h5Url", ""),
                "source": vm.get("author") or vm.get("showname", ""),
                "date": vm.get("publishTime", ""),
                "snippet": clean_text(vm.get("content", "")),
            }
            if extra:
                item["extra"] = extra
            results.append(item)

        elif cname.endswith("card445"):
            for img in vm.get("images") or []:
                if isinstance(img, dict):
                    images.append(_compact_dict({
                        "title": clean_text(img.get("title", "")),
                        "image_url": img.get("img", ""),
                        "detail_url": img.get("url", ""),
                        "width": img.get("width"),
                        "height": img.get("height"),
                    }))

        elif cname.endswith("card11052201"):
            for vid in vm.get("videoList") or []:
                if isinstance(vid, dict):
                    videos.append(_compact_dict({
                        "title": clean_text(vid.get("title", "")),
                        "url": vid.get("h5Url") or vid.get("nativeUrl", ""),
                        "video_src": vid.get("videoSrc", ""),
                        "cover": vid.get("cover", ""),
                        "author": vid.get("author", ""),
                        "duration": vid.get("duration", ""),
                        "publish_time": vid.get("publishTime", ""),
                    }))

        elif cname.endswith(("card_hint_middle", "card_bottom_hint")):
            for h in vm.get("hints") or []:
                if isinstance(h, dict):
                    t = clean_text(h.get("text") or h.get("query") or "")
                    if t:
                        hints.append(t)
                elif isinstance(h, str) and h.strip():
                    hints.append(clean_text(h))

    return {
        "has_more": bool(cards_props.get("initialHasMore", False)),
        "results": results,
        "hints": hints,
        "ai_answer": ai_answer,
        "ai_sources": ai_sources,
        "follow_ups": follow_ups,
        "images": images,
        "videos": videos,
    }


def search_so_qq(
    query: str,
    page: int = 1,
    limit: int = 0,
    include_ai: bool = True,
    include_media: bool = True,
    raw_cards: bool = False,
) -> dict:
    cards_props, from_cache = _fetch_cards_props(query, page)
    if not cards_props:
        return {
            "meta": {
                "engine": "so_qq",
                "query": query,
                "page": page,
                "pages_fetched": 0,
                "has_more": False,
                "returned_count": 0,
                "cached": from_cache,
            },
            "results": [],
            "hints": [],
        }

    if raw_cards:
        return {
            "engine": "so_qq",
            "query": query,
            "page": page,
            "cached": from_cache,
            "cards": cards_props.get("initialCards", []),
        }

    all_results, seen_urls, all_hints = [], set(), []
    ai_answer, ai_sources, follow_ups = "", [], []
    images, videos = [], []
    has_more, pages_fetched, all_cached = False, 0, True

    cur_page = page
    while True:
        cur_props, cur_cached = (
            (cards_props, from_cache) if cur_page == page else _fetch_cards_props(query, cur_page)
        )
        if not cur_props:
            has_more = False
            break

        pages_fetched += 1
        all_cached = all_cached and cur_cached
        parsed = _extract_page(cur_props, start_rank=len(all_results) + 1)
        has_more = parsed["has_more"]

        if cur_page == page:
            ai_answer = parsed["ai_answer"]
            ai_sources = parsed["ai_sources"]
            follow_ups = parsed["follow_ups"]

        for item in parsed["results"]:
            u = item.get("url")
            if u and u in seen_urls:
                continue
            if u:
                seen_urls.add(u)
            item["rank"] = len(all_results) + 1
            all_results.append(item)

        all_hints.extend(parsed["hints"])
        images.extend(parsed["images"])
        videos.extend(parsed["videos"])

        if limit <= 0 or len(all_results) >= limit or not has_more or pages_fetched >= MAX_AUTO_PAGES:
            break
        cur_page += 1

    if limit > 0:
        all_results = all_results[:limit]

    resp = {
        "meta": {
            "engine": "so_qq",
            "query": query,
            "page": page,
            "pages_fetched": pages_fetched,
            "has_more": has_more,
            "returned_count": len(all_results),
            "cached": all_cached,
        },
        "results": all_results,
        "hints": list(dict.fromkeys(all_hints)),
    }

    if include_ai and (ai_answer or ai_sources):
        resp["ai_overview"] = {
            "answer": ai_answer,
            "citations": ai_sources,
            "follow_up_queries": list(dict.fromkeys(follow_ups)),
        }

    if include_media and (images or videos):
        resp["media"] = {"images": images, "videos": videos}

    return resp


class SoQQEngine(SearchEngine):
    name = "so_qq"
    label = "腾讯元宝搜索 (so.qq.com)"
    description = "中文网页、公众号、资讯、图文视频及 AI 溯源搜索，免密钥直连。"

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        include_ai: bool = True,
        include_media: bool = True,
        raw: bool = False,
    ) -> dict:
        return search_so_qq(
            query=query,
            page=page,
            limit=limit,
            include_ai=include_ai,
            include_media=include_media,
            raw_cards=raw,
        )
