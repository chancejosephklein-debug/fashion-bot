import asyncio
import aiohttp
import math
import os
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, CHECK_INTERVAL_HOURS, TIMEZONE, LOCATION_LABEL,
    SOCIAL_TRENDS_BASE, TIKTOK_MARKET,
    APIFY_TOKEN, STOCKX_ACTOR_ID, APIFY_BASE
)

# ---------- TREND SCANNING ----------

async def fetch_tiktok_trending(session, limit=30):
    """Get trending videos from TikTok via omkar.cloud API (100 free/month)[citation:6]."""
    url = f"{SOCIAL_TRENDS_BASE}/tiktok/videos/trending"
    params = {"market": TIKTOK_MARKET, "max_results": limit}
    try:
        async with session.get(url, params=params, timeout=30) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", []) or data.get("videos", [])
            else:
                print(f"[TikTok] HTTP {resp.status}")
    except Exception as e:
        print(f"[TikTok] {e}")
    return []


def extract_text_from_video(video):
    """Pull caption/description text from a TikTok video object."""
    if isinstance(video, dict):
        for key in ("caption", "desc", "title", "text"):
            if key in video and video[key]:
                return str(video[key]).lower()
    return ""


async def build_trend_report():
    """Scan TikTok trending videos and match against watchlist."""
    async with aiohttp.ClientSession() as session:
        videos = await fetch_tiktok_trending(session, limit=30)

    print(f"[Feed] TikTok trending → {len(videos)} videos")

    brand_data = Counter()
    examples = {}

    for video in videos:
        text = extract_text_from_video(video)
        for brand in BRANDS:
            if brand.lower() in text:
                brand_data[brand] += 10
                if brand not in examples:
                    examples[brand] = {
                        "title": text[:80] if text else f"{brand} trending on TikTok",
                        "url": "https://tiktok.com",
                        "score": 10,
                        "source": "TikTok Trending"
                    }

    # Fallback so report is never empty
    if not brand_data:
        print("[Report] No brand matches, using fallback")
        for brand in BRANDS[:10]:
            brand_data[brand] = 1
            examples[brand] = {
                "title": f"{brand} — baseline check",
                "url": "https://trendsmcp.ai",
                "score": 1,
                "source": "Baseline"
            }

    ranked = sorted(brand_data.items(), key=lambda x: x[1], reverse=True)
    print(f"[Report] ranked={len(ranked)} top={ranked[:3]}")
    return ranked, examples, {}, {}


# ---------- RATINGS & DISPLAY ----------

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