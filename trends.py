import asyncio
import aiohttp
import math
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, TIMEZONE, LOCATION_LABEL,
    APIFY_TOKEN, APIFY_BASE, TIKTOK_ACTOR, STOCKX_ACTOR, GRAILED_ACTOR,
)


async def run_actor(session, actor_id, payload, timeout=120):
    """Run an Apify actor and return (items, ok)."""
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}
    try:
        async with session.post(url, params=params, json=payload, timeout=timeout) as resp:
            if resp.status in (200, 201):
                return await resp.json(), True
            body = await resp.text()
            print(f"[Apify Error] {actor_id} → HTTP {resp.status} · {body[:150]}")
            return [], False
    except Exception as e:
        print(f"[Apify Exception] {actor_id}: {e}")
        return [], False


async def fetch_tiktok(session, brand):
    payload = {
        "searchQueries": [brand],
        "resultsPerPage": 3,
        "maxItems": 3,
    }
    return await run_actor(session, TIKTOK_ACTOR, payload, timeout=90)


async def fetch_stockx(session, brand):
    payload = {
        "startUrls": [brand],
        "maxItems": 3,
        "country": "US",
        "currency": "USD",
    }
    return await run_actor(session, STOCKX_ACTOR, payload, timeout=90)


async def fetch_grailed(session, brand):
    payload = {
        "keyword": brand,
        "results_wanted": 3,
    }
    return await run_actor(session, GRAILED_ACTOR, payload, timeout=90)


def safe_price(val):
    """Return a clean $ string or None."""
    if val is None:
        return None
    try:
        f = float(val)
        if f <= 0:
            return None
        return f"${f:,.0f}"
    except (TypeError, ValueError):
        return None


def fmt_price(p):
    return p if p else "DATA UNAVAILABLE"


async def build_trend_report():
    """
    Returns:
        ranked: list of (brand, score)
        extra: (brand_products dict, price_data dict)
        sources_ok: dict of source -> bool
    """
    if not APIFY_TOKEN:
        print("[Trends] No APIFY_TOKEN set")
        return [], ({}, {}), {"tiktok": False, "stockx": False, "grailed": False}

    sources_ok = {"tiktok": False, "stockx": False, "grailed": False}
    price_data = {}
    brand_scores = Counter()
    brand_products = {}

    async with aiohttp.ClientSession() as session:
        # ---- TikTok scan (parallel) ----
        tt_tasks = [fetch_tiktok(session, b) for b in BRANDS[:10]]
        tt_results = await asyncio.gather(*tt_tasks)

        any_tt_ok = False
        tiktok_hits = []
        for brand, (items, ok) in zip(BRANDS[:10], tt_results):
            if ok:
                any_tt_ok = True
            if items:
                tiktok_hits.append((brand, items))

        sources_ok["tiktok"] = any_tt_ok

        for brand, videos in tiktok_hits:
            total = 0
            top_title = None
            top_engagement = 0
            for v in videos:
                play = v.get("playCount", 0) or 0
                like = v.get("diggCount", 0) or 0
                eng = play + (like * 2)
                total += eng
                if eng > top_engagement:
                    top_engagement = eng
                    top_title = (v.get("text") or "")[:70] or None
            brand_scores[brand] = total
            brand_products[brand] = top_title

        # ---- Price lookups for top brands (parallel) ----
        top_brands = [b for b, _ in brand_scores.most_common(5)]

        async def get_prices(brand):
            stockx_items, sx_ok = await fetch_stockx(session, brand)
            grailed_items, gr_ok = await fetch_grailed(session, brand)
            return brand, stockx_items, sx_ok, grailed_items, gr_ok

        price_results = await asyncio.gather(*[get_prices(b) for b in top_brands])

        for brand, stockx_items, sx_ok, grailed_items, gr_ok in price_results:
            if sx_ok:
                sources_ok["stockx"] = True
            if gr_ok:
                sources_ok["grailed"] = True

            sx_ask = None
            sx_title = None
            if stockx_items:
                p = stockx_items[0]
                sx_ask = safe_price(p.get("lowestAsk") or p.get("price"))
                sx_title = (p.get("title") or p.get("name") or "")[:60] or None

            gr_sold = None
            gr_title = None
            if grailed_items:
                g = grailed_items[0]
                gr_sold = safe_price(g.get("soldPrice") or g.get("price"))
                gr_title = (g.get("title") or g.get("name") or "")[:60] or None

            price_data[brand] = {
                "stockx_ask": sx_ask,
                "stockx_title": sx_title,
                "grailed_sold": gr_sold,
                "grailed_title": gr_title,
            }

        ranked = sorted(brand_scores.items(), key=lambda x: x[1], reverse=True)
        print(f"[Report] ranked={len(ranked)} sources={sources_ok}")
        return ranked, (brand_products, price_data), sources_ok


def normalize_rating(score, top_score):
    if top_score <= 0:
        return 0.0
    try:
        r = (math.log1p(score) / math.log1p(top_score)) * 9.5
    except Exception:
        r = (score / top_score) * 9.5
    return round(min(r, 9.8), 1)


def progress_bar(value, max_val, length=10):
    if max_val <= 0:
        return "░" * length
    filled = int(round((value / max_val) * length))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


def format_report_embed(ranked, extra, sources_ok, top_n=8):
    brand_products, price_data = extra
    now = datetime.now(ZoneInfo(TIMEZONE))
    top_score = ranked[0][1] if ranked else 1

    header = (
        "```\n"
        "FASHIONFLIP\n"
        "MARKET INTELLIGENCE\n"
        "● LIVE SCAN\n"
        "```"
    )

    def src_icon(ok):
        return "✓" if ok else "⚠"

    source_line = (
        f"`TIKTOK {src_icon(sources_ok['tiktok'])}  ·  "
        f"STOCKX {src_icon(sources_ok['stockx'])}  ·  "
        f"GRAILED {src_icon(sources_ok['grailed'])}`"
    )

    fields = []

    # Top signal
    if ranked:
        top_brand = ranked[0][0]
        top_r = normalize_rating(ranked[0][1], top_score)
        top_product = brand_products.get(top_brand) or "—"
        top_bar = progress_bar(top_r, 10, 14)

        top_block = (
            f"**{top_brand.upper()}**\n"
            f"*{top_product}*\n\n"
            f"`{top_r} / 10`  {top_bar}\n"
            f"**TOP SIGNAL · HIGH ENGAGEMENT**"
        )
        fields.append({"name": "▎ #01 — TOP SIGNAL", "value": top_block, "inline": False})

    # Rankings
    if len(ranked) > 1:
        lines = []
        for i, (brand, score) in enumerate(ranked[1:top_n], start=2):
            r = normalize_rating(score, top_score)
            bar = progress_bar(r, 10, 10)
            product = brand_products.get(brand)
            product_line = f"\n      *{product}*" if product else ""
            lines.append(f"`{i:02d}` **{brand.upper()}**{product_line}\n      `{r}` {bar}")
        fields.append({"name": "▎ RANKINGS", "value": "\n\n".join(lines), "inline": False})

    # Live market data
    price_lines = []
    for brand in [b for b, _ in ranked[:3]]:
        pd = price_data.get(brand, {})
        block = [f"**{brand.upper()}**"]
        block.append(f"StockX ask   ·  {fmt_price(pd.get('stockx_ask'))}")
        block.append(f"Grailed sold ·  {fmt_price(pd.get('grailed_sold'))}")
        price_lines.append("\n".join(block))

    if price_lines:
        fields.append({
            "name": "▎ LIVE MARKET DATA",
            "value": "\n\n".join(price_lines),
            "inline": False,
        })

    # Data sources
    src_block = "\n".join([
        f"TikTok          {src_icon(sources_ok['tiktok'])}",
        f"StockX          {src_icon(sources_ok['stockx'])}",
        f"Grailed         {src_icon(sources_ok['grailed'])}",
        f"Google Trends   ⚠",
    ])
    fields.append({"name": "▎ DATA SOURCES", "value": f"```\n{src_block}\n```", "inline": False})

    top_r = normalize_rating(top_score, top_score)
    if top_r >= 8.5:
        color = 0xC0392B
    elif top_r >= 7.0:
        color = 0xD35400
    elif top_r >= 5.5:
        color = 0xF39C12
    else:
        color = 0x7F8C8D

    scan_time = now.strftime("%d %b %Y · %I:%M %p")
    sources_count = sum(1 for v in sources_ok.values() if v)

    return {
        "title": None,
        "description": header + "\n" + source_line,
        "color": color,
        "fields": fields,
        "footer": {
            "text": (
                f"SCAN COMPLETE · {scan_time} · "
                f"Sources: {sources_count}/3 · Products: {len(ranked)}"
            )
        },
        "timestamp": now.isoformat(),
    }
