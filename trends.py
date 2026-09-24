import asyncio
import aiohttp
from collections import Counter
from datetime import datetime
from config import BRANDS, SUBREDDITS, HYPE_KEYWORDS, CHECK_INTERVAL_HOURS

HEADERS = {"User-Agent": "FashionTrendBot/1.0"}


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


async def scan_reddit_trends():
    brand_scores = Counter()
    brand_examples = {}

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_subreddit_hot(session, sub) for sub in SUBREDDITS]
        results = await asyncio.gather(*tasks)

    for posts in results:
        for post in posts:
            p = post.get("data", {})
            title = p.get("title", "").lower()
            selftext = p.get("selftext", "").lower()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            text = f"{title} {selftext}"
            permalink = f"https://reddit.com{p.get('permalink', '')}"

            engagement = score + (comments * 2)
            hype_bonus = sum(3 for kw in HYPE_KEYWORDS if kw in text)

            for brand in BRANDS:
                if brand.lower() in text:
                    brand_scores[brand] += engagement + hype_bonus
                    if brand not in brand_examples or engagement > brand_examples[brand]["score"]:
                        brand_examples[brand] = {
                            "title": p.get("title", ""),
                            "url": permalink,
                            "score": engagement,
                            "subreddit": p.get("subreddit", "")
                        }

    return brand_scores, brand_examples


def get_google_trends_scores():
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360)
        scores = {}
        chunks = [BRANDS[i:i+5] for i in range(0, len(BRANDS), 5)]

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


async def build_trend_report():
    reddit_scores, examples = await scan_reddit_trends()
    google_scores = await asyncio.to_thread(get_google_trends_scores)

    combined = {}
    for brand in BRANDS:
        r = reddit_scores.get(brand, 0)
        g = google_scores.get(brand, 0)
        combined[brand] = (r * 0.6) + (g * 10 * 0.4)

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return ranked, examples, reddit_scores, google_scores


def format_report(ranked, examples, reddit_scores, google_scores, top_n=10):
    now = datetime.utcnow().strftime("%b %d, %H:%M UTC")
    lines = [f"**🔥 Fashion Resale Trend Report — {now}**\n"]

    for i, (brand, score) in enumerate(ranked[:top_n], 1):
        emoji = "🚀" if i <= 3 else "📈" if i <= 6 else "👀"
        r = reddit_scores.get(brand, 0)
        g = google_scores.get(brand, 0)
        lines.append(f"{emoji} **#{i} {brand}** — Score `{score:.0f}` (Reddit `{r}` · Google `{g}`)")
        if brand in examples:
            ex = examples[brand]
            title = ex['title'][:80].replace('\n', ' ')
            lines.append(f"   ↳ *\"{title}\"* — [link]({ex['url']})")

    lines.append("\n**💡 Tip:** Top brands with rising Google + Reddit = best flip candidates.")
    lines.append(f"*Next auto-scan in {CHECK_INTERVAL_HOURS}h*")
    return "\n".join(lines)


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