"""Chinese social sentiment data sources for A-share stocks.

Replaces StockTwits (US retail) and Reddit (US discussion) with the
two dominant Chinese stock-discussion platforms:

  1. Guba East Money (东方财富股吧) — the largest A-share retail investor
     forum. Each stock has a dedicated board with user posts, read/reply
     counts, and author info. No authentication required.
  2. Xueqiu (雪球) — a Chinese investment social network with professional
     and semi-professional investor discussions. The public API requires
     a session cookie, so the fallback returns a placeholder when the
     endpoint is unreachable.

Both functions degrade gracefully and return a formatted plaintext block
ready for prompt injection. The caller never has to special-case None or
exceptions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from parsel import Selector

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; TradingAgents/0.2; +https://github.com/TauricResearch/TradingAgents)"
_GUBA_LIST_URL = "https://guba.eastmoney.com/list,{code}.html"
_XUEQIU_TIMELINE_URL = "https://xueqiu.com/statuses/stock_timeline.json?symbol_id={symbol_id}&count={count}&source=all"


def _extract_code(symbol: str) -> str:
    """Extract the numeric stock code from a symbol like ``000001.SZ`` or ``000001``."""
    return symbol.split(".")[0].split("_")[0].strip()


def _xueqiu_symbol_id(symbol: str) -> str:
    """Convert a symbol to a Xueqiu symbol ID (e.g. ``SZ000001`` or ``SH600000``)."""
    code = _extract_code(symbol)
    upper = symbol.upper()
    if ".SZ" in upper or "SZ" in code:
        return f"SZ{code}"
    return f"SH{code}"


def fetch_guba_posts(symbol: str, limit: int = 20, timeout: float = 10.0) -> str:
    """Fetch recent forum posts from East Money Guba for ``symbol``.

    Returns a formatted plaintext block with post titles, author, read/reply
    counts, and timestamps. Returns a placeholder string on any failure.
    """
    code = _extract_code(symbol)
    url = _GUBA_LIST_URL.format(code=code)
    req = Request(url, headers={"User-Agent": _UA})

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            html = raw.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("Guba fetch failed for %s: %s", symbol, exc)
        return f"<guba unavailable for {symbol}: {type(exc).__name__}>"

    sel = Selector(text=html)
    rows = sel.css("table.default_list tbody.listbody tr.listitem")

    if not rows:
        # The page still loaded but JS-rendered content is empty
        return f"<guba: no forum posts found for {code}>"

    posts = []
    bullish = bearish = neutral = 0
    for row in rows[:limit]:
        title_el = row.css("td div.title a")
        title = "".join(title_el.css("::text").getall()).strip() if title_el else ""

        read_str = row.css("td div.read::text").get(default="0").strip()
        reply_str = row.css("td div.reply::text").get(default="0").strip()

        author_el = row.css("td div.author a")
        author = author_el.css("::text").get(default="?").strip()

        update = row.css("td div.update::text").get(default="").strip()

        try:
            reads = int(read_str)
        except ValueError:
            reads = 0
        try:
            replies = int(reply_str)
        except ValueError:
            replies = 0

        # Attempt a crude bullish / bearish heuristic from the title text
        lower_title = title.lower()
        is_bullish = any(kw in lower_title for kw in ["涨", "牛", "买", "多", "好", "赚", "红", "利好", "底"])
        is_bearish = any(kw in lower_title for kw in ["跌", "熊", "卖", "空", "亏", "绿", "利空", "套", "跑"])

        if is_bullish and not is_bearish:
            tag = "看多"
            bullish += 1
        elif is_bearish and not is_bullish:
            tag = "看空"
            bearish += 1
        else:
            tag = "中性"
            neutral += 1

        posts.append({
            "title": title,
            "reads": reads,
            "replies": replies,
            "author": author,
            "updated": update,
            "tag": tag,
        })

    total = len(posts)
    lines = [f"东方财富股吧 - {code} (最近 {total} 条帖子):"]

    for p in posts:
        lines.append(
            f"  [{p['updated']} · {p['author']} · {p['tag']} · "
            f"阅读:{p['reads']} 评论:{p['replies']}] {p['title']}"
        )

    if total > 0:
        bull_pct = round(100 * bullish / total)
        bear_pct = round(100 * bearish / total)
        summary = (
            f"看多: {bullish} ({bull_pct}%) · "
            f"看空: {bearish} ({bear_pct}%) · "
            f"中性: {neutral} ({neutral}%) · "
            f"总计: {total} 条帖子"
        )
        return summary + "\n\n" + "\n".join(lines)

    return f"<guba: no forum posts found for {code}>"


def fetch_xueqiu_posts(symbol: str, limit: int = 20, timeout: float = 10.0) -> str:
    """Fetch recent Xueqiu (雪球) investor posts for ``symbol``.

    Xueqiu's public API requires an ``xq_a_token`` cookie.  This function
    first attempts to fetch a session cookie from the homepage, then uses
    it to call the stock timeline API.

    Returns a placeholder string if the endpoint is unreachable, returns
    no results, or the session is unauthenticated — the caller never has
    to handle exceptions.
    """
    code = _extract_code(symbol)
    symbol_id = _xueqiu_symbol_id(symbol)

    # Step 1: get a session cookie from the homepage
    cookie_jar = {}
    try:
        home_req = Request(
            "https://xueqiu.com/",
            headers={"User-Agent": _UA},
        )
        with urlopen(home_req, timeout=timeout) as resp:
            for c in resp.headers.get_all("Set-Cookie") or []:
                parts = c.split(";")[0].split("=", 1)
                if len(parts) == 2:
                    cookie_jar[parts[0]] = parts[1]
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("Xueqiu cookie fetch failed: %s", exc)
        return f"<xueqiu unavailable for {code}: {type(exc).__name__}>"

    xq_token = cookie_jar.get("xq_a_token", "")
    if not xq_token:
        # The homepage didn't set a token; grace to next path
        logger.warning("Xueqiu did not set xq_a_token cookie")

    # Step 2: call the stock timeline API
    url = _XUEQIU_TIMELINE_URL.format(symbol_id=symbol_id, count=min(limit, 50))
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_jar.items())
    api_req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Cookie": cookie_str,
            "Referer": f"https://xueqiu.com/S/{symbol_id}",
        },
    )

    try:
        with urlopen(api_req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Xueqiu API fetch failed for %s: %s", symbol, exc)
        return f"<xueqiu unavailable for {code}: {type(exc).__name__}>"

    statuses = data.get("list") if isinstance(data, dict) else []
    if not statuses:
        return f"<xueqiu: no posts found for {code}>"

    bullish = bearish = neutral = 0
    lines = [f"雪球 - {code} (最近 {len(statuses[:limit])} 条讨论):"]
    for s in statuses[:limit]:
        # Xueqiu status format
        text = (s.get("text") or "").replace("\n", " ").strip()
        if len(text) > 200:
            text = text[:200] + "..."

        created = s.get("created_at", "")
        if created:
            try:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                created = dt.strftime("%m-%d %H:%M")
            except (OSError, ValueError):
                created = str(created)

        user = (s.get("user") or {}).get("screen_name", "?")
        reply_count = s.get("reply_count", 0)
        retweet_count = s.get("retweet_count", 0)

        # Heuristic sentiment from text
        lower = text.lower()
        is_bullish = any(kw in lower for kw in ["涨", "牛", "买", "多", "好", "赚", "红", "底"])
        is_bearish = any(kw in lower for kw in ["跌", "熊", "卖", "空", "亏", "绿", "套", "跑"])

        if is_bullish and not is_bearish:
            tag = "看多"
            bullish += 1
        elif is_bearish and not is_bullish:
            tag = "看空"
            bearish += 1
        else:
            tag = "中性"
            neutral += 1

        lines.append(
            f"  [{created} · {user} · {tag} · "
            f"回复:{reply_count} 转发:{retweet_count}] {text}"
        )

    total = bullish + bearish + neutral
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"看多: {bullish} ({bull_pct}%) · "
        f"看空: {bearish} ({bear_pct}%) · "
        f"中性: {neutral} ({neutral}%) · "
        f"总计: {total} 条讨论"
    )
    return summary + "\n\n" + "\n".join(lines)
