import asyncio
import aiohttp
import os
import math
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, CHECK_INTERVAL_HOURS,
    TIMEZONE, LOCATION_LABEL,
)

TRENDSMCP_API_KEY = os.getenv("TRENDSMCP_API_KEY")
TRENDSMCP_URL = "https://api.trendsmcp.ai/api"


async def fetch_growth(session, keyword, sources, windows):
    """Get growth % for a keyword across multiple sources. Counts as 1 request per source."""
    results = {}
    for source in sources:
        body = {
            "mode": "get_growth",
            "source": source,
            "keyword": keyword,
            "percent_growth": windows,
        }
        headers = {
            "Authorization": f"Bearer {TRENDSMCP_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            async with session.post(
                TRENDSMCP_URL, headers=headers, json=body, timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results[source] = data.get("results", [])
                else:
                    print(f"[TrendsMCP] {source}/{keyword} → HTTP {resp.status}")
        except Exception as e:
            print(f"[TrendsMCP] {source}/{keyword}: {e}")
    return results


async def build_trend_report():
    """Query TrendsMCP for each brand across TikTok, Google, Instagram."""
    sources = ["tiktok", "google search", "amazon"]
    windows = ["7D", "30D"]

    # Limit to 15 brands to stay under request budget
    # 15 brands × 3 sources = 45 requests per scan
    watchlist = BRANDS[:15]

    brand_data = Counter()
    examples = {}

    async with aiohttp.ClientSession() as session:
        # Sequential with small delay to avoid rate limits
        for brand in watchlist:
            results = await fetch_growth(session, brand, sources, windows)
            for source, rows in results.items():
                for row in rows:
                    growth = row.get("growth", 0) or 0
                    direction = row.get("direction", "flat")
                    period = row.get("period", "30D")

                    # Weight by source and window
                    source_weight = {"tiktok": 1.5, "google search": 1.0, "amazon": 0.8}.get(source, 1.0)
                    window_weight = {"7D": 1.5, "30D": 1.0}.get(period, 1.0)

                    # Positive growth = score
                    score = max(0, growth) * source_weight * window_weight
                    brand_data[brand] += score

                    if brand not in examples:
                        examples[brand] = {
                            "title": f"{brand} — {growth:+.0f}% on {source} ({period})",
                            "url": f"https://trendsmcp.ai",
                            "score": score,
                            "subreddit": source,
                        }
            await asyncio.sleep(0.5)

    ranked = sorted(brand_data.items(), key=lambda x: x[1], reverse=True)
    print(f"[Report] ranked={len(ranked)} top={ranked[:3] if ranked else 'none'}")
    return ranked, examples, {}, {}


# ---- DISPLAY FUNCTIONS (unchanged from before) ----

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
        fields.append({"name": "🎯 On the Radar", "value": "\n".join(runners), "inline": False})

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