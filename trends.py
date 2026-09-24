import asyncio
import aiohttp
import re
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, SUBREDDITS, HYPE_KEYWORDS, CHECK_INTERVAL_HOURS,
    TIMEZONE, LOCATION_LABEL,
)

HEADERS = {"User-Agent": "FashionTrendBot/1.0"}

# Brand patterns to auto-discover from post titles
# Capitalized words, 1-3 tokens, not common English words
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "my", "your",
    "his", "her", "its", "our", "their", "what", "which", "who", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "now", "new", "used",
    "help", "please", "anyone", "someone", "need", "want", "looking",
    "selling", "buying", "price", "check", "legit", "real", "fake",
    "worth", "still", "best", "good", "bad", "hot", "cold", "red", "blue",
    "black", "white", "green", "size", "small", "medium", "large",
    "reddit", "discord", "post", "comment", "hey", "hi", "hello",
    "thanks", "thank", "lol", "wtb", "wts", "iso", "fs", "ft", "usa",
    "uk", "eu", "dm", "pm", "pp", "shipping", "ship", "sold", "buy",
    "qc", "rep", "reps", "batch", "link", "links", "today", "yesterday",
    "week", "month", "year", "day", "time", "hour", "minute",
}

BRAND_PATTERN = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,2})\b")


async def fetch_subreddit_hot(session, subreddit, limit=100):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        async with session.get(url, headers=HEADERS, timeout=15) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"[Reddit] r/{subreddit}: {e}")
        return []


def extract_candidate_brands(text):
    """Pull brand-like tokens from post text."""
    candidates = []
    for match in BRAND_PATTERN.findall(text):
        # Skip stopwords
        words = match.split()
        if any(w.lower() in STOPWORDS for w in words):
            continue
        if len(match) < 4:
            continue
        candidates.append(match)
    return candidates


async def scan_reddit_trends(extra_brands):
    """Scan Reddit and score both known brands and discovered brands."""
    brand_scores = Counter()
    brand_examples = {}
    discovered = Counter()

    all_brands = list(set(BRANDS + extra_brands))
    all_brands_lower = {b.lower(): b for b in all_brands}

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_subreddit_hot(session, sub) for sub in SUBREDDITS]
        results = await asyncio.gather(*tasks)

    for posts in results:
        for post in posts:
            p = post.get("data", {})
            title = p.get("title", "")
            selftext = p.get("selftext", "")
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            text = f"{title} {selftext}"
            text_lower = text.lower()
            permalink = f"https://reddit.com{p.get('permalink', '')}"

            engagement = score + (comments * 2)
            hype_bonus = sum(4 for kw in HYPE_KEYWORDS if kw in text_lower)
            post_value = engagement + hype_bonus

            # Score known brands
            for brand_lower, brand in all_brands_lower.items():
                if brand_lower in text_lower:
                    brand_scores[brand] += post_value
                    if brand not in brand_examples or post_value > brand_examples[brand]["score"]:
                        brand_examples[brand] = {
                            "title": title,
                            "url": permalink,
                            "score": post_value,
                            "subreddit": p.get("subreddit", "")
                        }

            # Discover new brand candidates
            for cand in extract_candidate_brands(title):
                if cand.lower() not in all_brands_lower:
                    discovered[cand] += post_value

    return brand_scores, brand_examples, discovered


def get_google_trends_scores(brands):
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360)
        scores = {}
        chunks = [brands[i:i+5] for i in range(0, len(brands), 5)]

        for chunk in chunks:
            try:
                pytrends.build_payload(chunk, timeframe="now 7-d")
                df = pytrends.interest_over_time()
                if not df.empty:
                    for brand in chunk:
                        if brand in df.columns:
                            scores[brand] = int(df[brand].mean())
            except Exception as e:
                print(f"[GoogleTrends] {chunk}: {e}")
                continue
        return scores
    except Exception as e:
        print(f"[GoogleTrends] fatal: {e}")
        return {}


def normalize_rating(raw_score, top_score):
    """Convert raw score to a 0-10 rating with one decimal."""
    if top_score <= 0:
        return 0.0
    rating = (raw_score / top_score) * 10
    return round(rating, 1)


async def build_trend_report(previous_discovered=None):
    """Build a ranked report. Includes auto-discovered brands."""
    previous_discovered = previous_discovered or []

    reddit_scores, examples, discovered = await scan_reddit_trends(previous_discovered)

    # Take top new discoveries and give them a small boost so they appear
    top_discovered = [b for b, _ in discovered.most_common(20)]
    # Only keep discoveries that aren't already in the base list
    fresh_discoveries = [b for b in top_discovered if b not in reddit_scores]

    # Merge discovered scores in
    for brand, val in discovered.most_common(20):
        if brand not in reddit_scores:
            # Discount discovered brands slightly (unknown reliability)
            reddit_scores[brand] = int(val * 0.7)

    # Pull google trends for top candidates only (to avoid rate limits)
    top_candidates = [b for b, _ in reddit_scores.most_common(15)]
    google_scores = await asyncio.to_thread(get_google_trends_scores, top_candidates)

    # Combine
    combined = {}
    for brand, r_score in reddit_scores.items():
        g = google_scores.get(brand, 0)
        combined[brand] = (r_score * 0.6) + (g * 10 * 0.4)

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return ranked, examples, reddit_scores, google_scores, fresh_discoveries


def rating_emoji(rating):
    if rating >= 9.0:
        return "🔥"
    if rating >= 7.5:
        return "🚀"
    if rating >= 6.0:
        return "📈"
    if rating >= 4.0:
        return "👀"
    return "💤"


def rating_label(rating):
    if rating >= 9.0:
        return "HOT"
    if rating >= 7.5:
        return "Strong"
    if rating >= 6.0:
        return "Rising"
    if rating >= 4.0:
        return "Watch"
    return "Quiet"


def get_local_time():
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    return now


def format_report_embed(ranked, examples, fresh_discoveries, top_n=12):
    """Return a Discord embed dict."""
    now = get_local_time()
    date_line = now.strftime("%A, %B %d, %Y")
    time_line = now.strftime("%-I:%M %p").replace("AM", "AM").replace("PM", "PM")

    top_score = ranked[0][1] if ranked else 0

    lines = []
    for i, (brand, score) in enumerate(ranked[:top_n], 1):
        rating = normalize_rating(score, top_score)
        emoji = rating_emoji(rating)
        label = rating_label(rating)
        lines.append(f"{emoji} **{brand}** — `{rating}/10` · *{label}*")

    description = "\n".join(lines)

    # Spike/rising section
    movers = []
    for brand, score in ranked[top_n:top_n+5]:
        rating = normalize_rating(score, top_score)
        movers.append(f"`{rating}/10` · {brand}")

    fields = []

    if fresh_discoveries:
        fresh_str = " · ".join(f"**{b}**" for b in fresh_discoveries[:5])
        fields.append(("🆕 Just Popped Up", fresh_str, False))

    if movers:
        fields.append(("🎯 Also Worth Watching", "\n".join(movers), False))

    # Top pick with link
    if ranked and ranked[0][0] in examples:
        ex = examples[ranked[0][0]]
        title = ex["title"][:100].replace("\n", " ")
        fields.append((
            f"💬 Top Pick Buzz: {ranked[0][0]}",
            f"[*\"{title}\"*]({ex['url']})",
            False,
        ))

    # Color based on top rating
    top_rating = normalize_rating(top_score, top_score)
    if top_rating >= 9:
        color = 0xFF3B30  # red = HOT
    elif top_rating >= 7.5:
        color = 0xFF9500  # orange
    elif top_rating >= 6:
        color = 0xFFCC00  # yellow
    else:
        color = 0x34C759  # green

    embed = {
        "title": "🔥 Fashion Resale Trend Report",
        "description": description,
        "color": color,
        "fields": [
            {"name": name, "value": val, "inline": inline}
            for name, val, inline in fields
        ],
        "footer": {
            "text": f"📍 {LOCATION_LABEL} · {date_line} · {time_line} · next scan in {CHECK_INTERVAL_HOURS}h"
        },
    }
    return embed


def detect_spikes(current, previous, threshold=4):
    if not previous:
        return []
    prev_map = {b: i for i, (b, _) in enumerate(previous)}
    spikes = []
    for i, (brand, score) in enumerate(current):
        prev_pos = prev_map.get(brand)
        if prev_pos is not None and (prev_pos - i) >= threshold:
            spikes.append((brand, prev_pos - i, score))
    return spikes