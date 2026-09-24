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
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}
    try:
        async with session.post(url, params=params, json=payload, timeout=timeout) as resp:
            if resp.status in (200, 201):
                return await resp.json()
            print(f"[Apify] {actor_id} → HTTP {resp.status}")
    except Exception as e:
        print(f"[Apify] {actor_id}: {e}")
    return []


async def get_tiktok_trends(session):
    results = {}
    for brand in BRANDS[:10]:
        payload = {
            "searchQueries": [brand],
            "resultsPerPage": 3,
            "maxItems": 3,
        }
        items = await run_actor(session, TIKTOK_ACTOR, payload, timeout=90)
        if items:
            results[brand] = items
    return results


async def get_stockx_prices(session, brand):
    payload = {
        "searchQuery": brand,
        "maxItems": 3,
        "country": "US",
        "currency": "USD",
    }
    return await run_actor(session, STOCKX_ACTOR, payload, timeout=90)


async def get_grailed_sold(session, brand):
    payload = {
        "query": brand,
        "sort": "sold",
        "maxItems": 5,
    }
    return await run_actor(session, GRAILED_ACTOR, payload, timeout=90)


async def build_trend_report():
    if not APIFY_TOKEN:
        print("[Trends] No APIFY_TOKEN set")
        return [], {}, {}

    async with aiohttp.ClientSession() as session:
        tiktok_data = await get_tiktok_trends(session)

        brand_scores = Counter()
        examples = {}

        for brand, videos in tiktok_data.items():
            total = 0
            for v in videos:
                play = v.get("playCount", 0) or 0
                like = v.get("diggCount", 0) or 0
                total += play + (like * 2)
            brand_scores[brand] = total
            if videos:
                examples[brand] = {
                    "title": (videos[0].get("text") or f"{brand} on TikTok")[:100],
                    "url": videos[0].get("webVideoUrl", "https://tiktok.com"),
                    "source": "TikTok",
                }

        top_brands = [b for b, _ in brand_scores.most_common(5)]
        price_data = {}

        for brand in top_brands:
            stockx = await get_stockx_prices(session, brand)
            grailed = await get_grailed_sold(session, brand)
            price_data[brand] = {
                "stockx": stockx[:3] if stockx else [],
                "grailed": grailed[:3] if grailed else [],
            }
            await asyncio.sleep(1)

        ranked = sorted(brand_scores.items(), key=lambda x: x[1], reverse=True)
        print(f"[Report] ranked={len(ranked)}")
        return ranked, examples, price_data


def normalize_rating(score, top_score):
    if top_score <= 0:
        return 0.0
    try:
        r = (math.log1p(score) / math.log1p(top_score)) * 9.5
    except Exception:
        r = (score / top_score) * 9.5
    return round(min(r, 9.8), 1)


def rating_emoji(r):
    if r >= 8.5: return "🔥"
    if r >= 7.0: return "🚀"
    if r >= 5.5: return "📈"
    if r >= 3.5: return "👀"
    return "💤"


def format_report_embed(ranked, examples, price_data, top_n=8):
    now = datetime.now(ZoneInfo(TIMEZONE))
    top_score = ranked[0][1] if ranked else 1

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = []
    for i, (brand, score) in enumerate(ranked[:top_n]):
        r = normalize_rating(score, top_score)
        marker = medals.get(i, f"`#{i+1:02d}`")
        bar = "▰" * int(round(r / 1.25)) + "▱" * (8 - int(round(r / 1.25)))
        lines.append(f"{marker} **{brand}** — `{r}/10` {bar} {rating_emoji(r)}")

    description = "\n".join(lines)
    fields = []

    if ranked and ranked[0][0] in examples:
        ex = examples[ranked[0][0]]
        fields.append({
            "name": f"💬 Top Signal — {ranked[0][0]}",
            "value": f"[*{ex['title']}*]({ex['url']})\n*{ex['source']}*",
            "inline": False,
        })

    for brand in [b for b, _ in ranked[:3]]:
        if brand in price_data and price_data[brand]["stockx"]:
            p = price_data[brand]["stockx"][0]
            name = (p.get("title") or p.get("name") or brand)[:60]
            ask = p.get("lowestAsk") or p.get("price") or "?"
            fields.append({
                "name": f"💸 {brand} — StockX",
                "value": f"**{name}**\nLowest Ask: `${ask}`",
                "inline": True,
            })
        if brand in price_data and price_data[brand]["grailed"]:
            g = price_data[brand]["grailed"][0]
            name = (g.get("title") or g.get("name") or brand)[:60]
            sold = g.get("soldPrice") or g.get("price") or "?"
            fields.append({
                "name": f"📊 {brand} — Grailed Sold",
                "value": f"**{name}**\nSold: `${sold}`",
                "inline": True,
            })

    top_r = normalize_rating(top_score, top_score)
    if top_r >= 8.5: color = 0xE74C3C
    elif top_r >= 7.0: color = 0xE67E22
    elif top_r >= 5.5: color = 0xF1C40F
    else: color = 0x2ECC71

    footer = now.strftime("%a %b %d · %-I:%M %p")

    return {
        "title": "🔥 Fashion Resale Trend Report",
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": f"📍 {LOCATION_LABEL} · {footer} · run !trends to refresh"},
        "timestamp": now.isoformat(),
    }
