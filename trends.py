import asyncio
import aiohttp
import math
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, CHECK_INTERVAL_HOURS, TIMEZONE, LOCATION_LABEL,
    TRENDSMCP_API_KEY, TRENDSMCP_URL,
)


async def fetch_top_trends(session, feed_type, limit=100):
    """Get live trending board for a feed type."""
    body = {
        "mode": "get_top_trends",
        "type": feed_type,
        "limit": limit,
    }
    headers = {
        "Authorization": f"Bearer {TRENDSMCP_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with session.post(TRENDSMCP_URL, headers=headers, json=body, timeout=30) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
            else:
                print(f"[TrendsMCP] top_trends/{feed_type} → HTTP {resp.status}")
    except Exception as e:
        print(f"[TrendsMCP] top_trends/{feed_type}: {e}")
    return []


async def fetch_trending_keywords(session, source, limit=100):
    """Fallback: get trending keywords from a source."""
    body = {
        "mode": "get_trending_keywords",
        "source": source,
        "limit": limit,
    }
    headers = {
        "Authorization": f"Bearer {TRENDSMCP_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with session.post(TRENDSMCP_URL, headers=headers, json=body, timeout=30) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
            else:
                print(f"[TrendsMCP] trending_keywords/{source} → HTTP {resp.status}")
    except Exception as e:
        print(f"[TrendsMCP] trending_keywords/{source}: {e}")
    return []


def extract_keyword(item):
    """Normalize various response shapes into a single keyword string."""
    if isinstance(item, str):
        return item.lower()
    if isinstance(item, list) and len(item) >= 2:
        return str(item[1]).lower()
    if isinstance(item, dict):
        for k in ("keyword", "name", "title", "hashtag", "query", "term"):
            if k in item:
                return str(item[k]).lower()
    return str(item).lower()


async def build_trend_report():
    """Get live trends and match against watchlist."""
    feeds = [
        "TikTok Trending Hashtags",
        "Google Trends",
        "TikTok Trending Sounds",
    ]

    brand_data = Counter()
    examples = {}
    raw_count = 0

    async with aiohttp.ClientSession() as session:
        for feed in feeds:
            items = await fetch_top_trends(session, feed, limit=100)
            if not items:
                items = await fetch_trending_keywords(session, feed.lower(), limit=100)
            raw_count += len(items)
            print(f"[Feed] {feed} → {len(items)} items")

            for item in items:
                keyword = extract_keyword(item)
                for brand in BRANDS:
                    if brand.lower() in keyword:
                        brand_data[brand] += 10
                        if brand not in examples:
                            examples[brand] = {
                                "title": f"Trending on {feed}: {keyword[:80]}",
                                "url": "https://trendsmcp.ai",
                                "score": 10,
                                "subreddit": feed,
                            }

    # Fallback so report is never empty
    if not brand_data:
        print(f"[Report] no matches (raw items: {raw_count}), using fallback")
        for brand in BRANDS[:10]:
            brand_data[brand] = 1
            examples[brand] = {
                "title": f"{brand} — baseline (no live spike detected)",
                "url": "https://trendsmcp.ai",
                "score": 1,
                "subreddit": "Baseline",
            }

    ranked = sorted(brand_data.items(), key=lambda x: x[1], reverse=True)
    print(f"[Report] ranked={len(ranked)} top={ranked[:3]}")
    return ranked, examples, {}, {}


def normalize_rating(score, top_score):
    if top_score <= 0:
        return 0.0
    try:
        r = (math.log1p(score) / math.log1p(top_score)) * 10
    except Exception:
        r = (score / top_score) * 10
    return round(min(r, 10.0), 1)


def rating_emoji(r):
    if r >= 9.0: return "🔥"
    if r >= 7.5: return "🚀"
    if r >= 6.0: return "📈"
    if r >= 4.0: return "👀"
    return "💤"


def rating_label(r):
    if r >= 9.0: return "HOT"
    if r >= 7.5: return "Strong"
    if r >= 6.0: return "Rising"
    if r >= 4.0: return "Watch"
    return "Quiet"


def format_report_embed(ranked, examples, reddit_scores, google_scores, top_n=10):
    now = datetime.now(ZoneInfo(TIMEZONE))
    top_score = ranked[0][1] if ranked else 1

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = []
    for i, (brand, score) in enumerate(ranked[:top_n]):
        r = normalize_rating(score, top_score)
        rank_marker = medals.get(i, f"`#{i+1:02d}`")
        bar_filled = int(round(r))
        bar = "▰" * bar_filled + "▱" * (10 - bar_filled)
        lines.append(
            f"{rank_marker} **{brand}**\n"
            f"   {rating_emoji(r)} `{r}/10` {bar} *{rating_label(r)}*"
        )

    description = "\n\n".join(lines)
    fields = []

    if ranked and ranked[0][0] in examples:
        ex = examples[ranked[0][0]]
        fields.append({
            "name": f"💬 Top Signal: {ranked[0][0]}",
            "value": f"*{ex['title']}*",
            "inline": False,
        })

    if len(ranked) > top_n:
        runners = []
        for brand, score in ranked[top_n:top_n+4]:
            r = normalize_rating(score, top_score)
            runners.append(f"`{r}` · **{brand}**")
        fields.append({
            "name": "🎯 On the Radar",
            "value": "\n".join(runners),
            "inline": False,
        })

    hot_count = sum(1 for b, s in ranked[:top_n] if normalize_rating(s, top_score) >= 7.5)
    if hot_count >= 5:
        market = "🔥 **Hot market** — multiple brands pumping. Good week to flip."
    elif hot_count >= 2:
        market = "📊 **Mixed market** — a couple strong plays, rest is quiet."
    else:
        market = "💤 **Slow market** — hold inventory, wait for next wave."
    fields.append({"name": "📊 Market Read", "value": market, "inline": False})

    top_r = normalize_rating(top_score, top_score)
    if top_r >= 9: color = 0xE74C3C
    elif top_r >= 7.5: color = 0xE67E22
    elif top_r >= 6: color = 0xF1C40F
    else: color = 0x2ECC71

    footer_time = now.strftime("%a %b %d · %-I:%M %p")

    return {
        "title": "🔥 Fashion Resale Trend Report",
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"📍 {LOCATION_LABEL} · {footer_time} · next scan in {CHECK_INTERVAL_HOURS}h"
        },
        "timestamp": now.isoformat(),
    }


def detect_spikes(current, previous, threshold=5, min_rating=6.0):
    if not previous:
        return []
    prev_map = {b: i for i, (b, _) in enumerate(previous)}
    top_score = current[0][1] if current else 1
    spikes = []
    for i, (brand, score) in enumerate(current[:15]):
        rating = normalize_rating(score, top_score)
        if rating < min_rating:
            continue
        prev_pos = prev_map.get(brand)
        if prev_pos is not None and (prev_pos - i) >= threshold:
            spikes.append((brand, prev_pos - i, rating))
    return spikes