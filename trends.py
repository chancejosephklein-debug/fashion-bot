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
    """Run an Apify actor and return dataset items."""
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}
    try:
        async with session.post(url, params=params, json=payload, timeout=timeout) as resp:
            if resp.status in (200, 201):
                return await resp.json()
            body = await resp.text()
            print(f"[Apify Error] {actor_id} → HTTP {resp.status} · {body[:200]}")
    except Exception as e:
        print(f"[Apify Exception] {actor_id}: {e}")
    return []

async def get_tiktok_trends(session):
    """Search TikTok for each brand and get engagement data in parallel."""
    async def fetch_brand(brand):
        payload = {
            "searchQueries": [brand],
            "resultsPerPage": 3,
            "maxItems": 3,
        }
        items = await run_actor(session, TIKTOK_ACTOR, payload, timeout=90)
        return brand, items

    tasks = [fetch_brand(brand) for brand in BRANDS[:10]]
    results = await asyncio.gather(*tasks)
    return {brand: items for brand, items in results if items}

async def get_stockx_prices(session, brand):
    """Get StockX resale prices for a brand."""
    payload = {
        "startUrls": [brand],
        "maxItems": 3,
        "country": "US",
        "currency": "USD",
    }
    return await run_actor(session, STOCKX_ACTOR, payload, timeout=90)

async def get_grailed_sold(session, brand):
    """Get Grailed sold prices — the REAL market price."""
    payload = {
        "keyword": brand,
        "results_wanted": 3,
    }
    return await run_actor(session, GRAILED_ACTOR, payload, timeout=90)

async def build_trend_report():
    """Orchestrates data fetching. Only runs when !trends is called."""
    if not APIFY_TOKEN:
        print("[Trends] No APIFY_TOKEN set")
        return [], {}, {}

    async with aiohttp.ClientSession() as session:
        tiktok_data = await get_tiktok_trends(session)
        print(f"[TikTok] got data for {len(tiktok_data)} brands")

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
            stockx, grailed = await asyncio.gather(
                get_stockx_prices(session, brand),
                get_grailed_sold(session, brand)
            )
            price_data[brand] = {
                "stockx": stockx[:3] if stockx else [],
                "grailed": grailed[:3] if grailed else [],
            }
            await asyncio.sleep(0.5)

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
    """Creates a clean, professional Discord embed with proper spacing."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    top_score = ranked[0][1] if ranked else 1

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    
    # Build a cleaner trend list with spacing between items
    trend_lines = []
    for i, (brand, score) in enumerate(ranked[:top_n]):
        r = normalize_rating(score, top_score)
        marker = medals.get(i, f"`#{i+1:02d}`")
        # Fixed-width bar for alignment
        bar_filled = int(round(r / 1.25))
        bar = "▰" * bar_filled + "▱" * (8 - bar_filled)
        trend_lines.append(
            f"{marker} **{brand}**\n"
            f"{rating_emoji(r)} `{r}/10` {bar}"
        )
    
    # Join with double newlines for clear separation between entries
    trend_description = "\n\n".join(trend_lines)
    
    fields = []

    # Top Signal section
    if ranked and ranked[0][0] in examples:
        ex = examples[ranked[0][0]]
        fields.append({
            "name": "💬 Top Signal",
            "value": f"**{ranked[0][0]}**\n[*\"{ex['title']}\"*]({ex['url']})\n*Source: {ex['source']}*",
            "inline": False,
        })

    # Price data section - group StockX and Grailed together per brand
    price_lines = []
    for brand in [b for b, _ in ranked[:3]]:
        if brand in price_data:
            brand_lines = [f"**{brand}**"]
            
            if price_data[brand]["stockx"]:
                p = price_data[brand]["stockx"][0]
                name = (p.get("title") or p.get("name") or brand)[:60]
                ask = p.get("lowestAsk") or p.get("price") or "?"
                brand_lines.append(f"  💸 StockX: `${ask}` — *{name}*")
            
            if price_data[brand]["grailed"]:
                g = price_data[brand]["grailed"][0]
                name = (g.get("title") or g.get("name") or brand)[:60]
                sold = g.get("soldPrice") or g.get("price") or "?"
                brand_lines.append(f"  📊 Grailed Sold: `${sold}` — *{name}*")
            
            price_lines.append("\n".join(brand_lines))
    
    if price_lines:
        fields.append({
            "name": "💰 Live Market Data",
            "value": "\n\n".join(price_lines),
            "inline": False,
        })

    # Market summary
    hot_count = sum(1 for b, s in ranked[:top_n] if normalize_rating(s, top_score) >= 7.0)
    if hot_count >= 4:
        market = "🔥 **Hot Market** — Multiple brands with strong momentum."
    elif hot_count >= 2:
        market = "📊 **Mixed Market** — A few clear opportunities."
    else:
        market = "💤 **Slow Market** — Limited activity right now."
    
    fields.append({
        "name": "📈 Market Read",
        "value": market,
        "inline": False,
    })

    top_r = normalize_rating(top_score, top_score)
    if top_r >= 8.5: color = 0xE74C3C
    elif top_r >= 7.0: color = 0xE67E22
    elif top_r >= 5.5: color = 0xF1C40F
    else: color = 0x2ECC71

    footer = now.strftime("%A, %B %d, %Y · %I:%M %p")

    return {
        "title": "🔥 Fashion Resale Trend Report",
        "description": trend_description,
        "color": color,
        "fields": fields,
        "footer": {"text": f"📍 {LOCATION_LABEL} · {footer} · Run !trends to refresh"},
        "timestamp": now.isoformat(),
    }
