import asyncio
import aiohttp
import re
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BRANDS, SUBREDDITS, HYPE_KEYWORDS, CHECK_INTERVAL_HOURS,
    TIMEZONE, LOCATION_LABEL,
)

HEADERS = {"User-Agent": "FashionTrendBot/1.0"}

# Noise filter — kill posts that aren't actually about resale/trends
NOISE_PATTERNS = re.compile(
    r"\b(grindr|tinder|hookup|dating|girlfriend|boyfriend|gf|bf|"
    r"selfie|fit pic|outfit of the day|ootd|"
    r"cringe|meme|shitpost|jerk|circlejerk|lol|haha|"
    r"best of|vote|poll|survey|"
    r"selling my|bought today|mail day|haul|"
    r"should i buy|is this real|legit check|lc)\b",
    re.IGNORECASE,
)

# Require at least one of these to consider a post "trend-relevant"
TREND_SIGNALS = [
    "restock", "drop", "dropping", "hyped", "grail", "resell",
    "resale", "worth", "price", "wtb", "wts", "iso", "for sale",
    "trending", "hype", "cop", "invest", "flip", "market",
    "sold out", "sell out", "back in stock", "restocking",
    "collab", "release", "upcoming", "sneaker", "jacket", "hoodie",
]


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


def is_trend_relevant(text):
    """Return True if post is about trends/resale, not random fit pics."""
    if NOISE_PATTERNS.search(text):
        return False
    lower = text.lower()
    return any(sig in lower for sig in TREND_SIGNALS)


async def scan_reddit_trends():
    brand_scores = Counter()
    brand_examples = {}
    brand_subs = defaultdict(set)

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
            subreddit = p.get("subreddit", "")
            permalink = f"https://reddit.com{p.get('permalink', '')}"

            # Skip noise + non-trend posts
            if not is_trend_relevant(text):
                continue

            # Signal weight
            engagement = min(score, 2000) + min(comments * 2, 500)
            hype_bonus = sum(5 for kw in HYPE_KEYWORDS if kw in text_lower)
            post_value = engagement + hype_bonus

            if post_value < 20:
                continue

            for brand in BRANDS:
                if brand.lower() in text_lower:
                    brand_scores[brand] += post_value
                    brand_subs[brand].add(subreddit)
                    # Prefer posts from trend-related subreddits
                    sub_boost = 100 if subreddit in (
                        "reselling", "sneakermarket", "FashionRepsBST",
                        "sneakers", "SupremeClothing",
                    ) else 0
                    weighted = post_value + sub_boost
                    if brand not in brand_examples or weighted > brand_examples[brand]["score"]:
                        brand_examples[brand] = {
                            "title": title[:110],
                            "url": permalink,
                            "score": weighted,
                            "subreddit": subreddit,
                        }

    return brand_scores, brand_examples, brand_subs


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
                print(f"[GT] {chunk}: {e}")
                continue
        return scores
    except Exception as e:
        print(f"[GT] fatal: {e}")
        return {}


async def build_trend_report():
    reddit_scores, examples, subs = await scan_reddit_trends()

    # Only request Google for brands that actually have Reddit traction
    candidates = [b for b, s in reddit_scores.most_common(20) if s > 0]
    google_scores = await asyncio.to_thread(get_google_trends_scores, candidates)

    combined = {}
    for brand, r in reddit_scores.items():
        if r <= 0:
            continue
        g = google_scores.get(brand, 0)
        combined[brand] = (r * 0.7) + (g * 15 * 0.3)

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return ranked, examples, reddit_scores, google_scores


def normalize_rating(score, top_score):
    if top_score <= 0:
        return 0.0
    # Use log scale so top isn't always 10 and mid-tier is compressed
    import math
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

    # Medal emojis for top 3
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

    # Top pick with real post quote
    if ranked and ranked[0][0] in examples:
        ex = examples[ranked[0][0]]
        quote = ex["title"].replace("|", "/")
        fields.append({
            "name": f"💬 Why {ranked[0][0]} is #1",
            "value": f"[*\"{quote}\"*]({ex['url']})\n*from r/{ex['subreddit']}*",
            "inline": False,
        })

    # Runners-up worth a look
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

    # Market read
    hot_count = sum(1 for b, s in ranked[:top_n] if normalize_rating(s, top_score) >= 7.5)
    if hot_count >= 5:
        market = "🔥 **Hot market** — multiple brands pumping. Good week to flip."
    elif hot_count >= 2:
        market = "📊 **Mixed market** — a couple strong plays, rest is quiet."
    else:
        market = "💤 **Slow market** — hold inventory, wait for next drop wave."
    fields.append({"name": "📊 Market Read", "value": market, "inline": False})

    # Color
    top_r = normalize_rating(top_score, top_score)
    if top_r >= 9: color = 0xE74C3C
    elif top_r >= 7.5: color = 0xE67E22
    elif top_r >= 6: color = 0xF1C40F
    else: color = 0x2ECC71

    footer_time = now.strftime("%a %b %d · %-I:%M %p")

    embed = {
        "title": "🔥 Fashion Resale Trend Report",
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"📍 {LOCATION_LABEL} · {footer_time} · auto-scan every {CHECK_INTERVAL_HOURS}h"
        },
        "timestamp": now.isoformat(),
    }
    return embed


def detect_spikes(current, previous, threshold=5, min_rating=6.0):
    """Only report spikes into the top-tier, no more list spam."""
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