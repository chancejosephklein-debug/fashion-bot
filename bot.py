import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
import json

from config import (
    DISCORD_TOKEN, TREND_CHANNEL_ID, ALERT_ROLE_ID, CHECK_INTERVAL_HOURS,
    TIMEZONE, LOCATION_LABEL,
    APIFY_TOKEN, STOCKX_ACTOR_ID, APIFY_BASE
)
from trends import (
    build_trend_report, format_report_embed, detect_spikes
)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
last_ranked = []


# ---------- STOCKX PRICE LOOKUP ----------

async def fetch_stockx_price(query):
    """Scrape StockX for real resale data via Apify[citation:14]."""
    url = f"{APIFY_BASE}/acts/{STOCKX_ACTOR_ID}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}
    payload = {
        "mode": "search",
        "searchQuery": query,
        "maxItems": 3,
        "fetchProductDetails": True,
        "currency": "USD",
        "useProxy": True
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, json=payload, timeout=90) as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[StockX] HTTP {resp.status}")
    except Exception as e:
        print(f"[StockX] {e}")
    return []


# ---------- CORE REPORT LOGIC ----------

async def post_report():
    global last_ranked
    channel = bot.get_channel(TREND_CHANNEL_ID)
    if not channel:
        print(f"[ERR] Channel {TREND_CHANNEL_ID} not found")
        return

    ranked, examples, reddit_scores, google_scores = await build_trend_report()

    if not ranked:
        await channel.send("⚠️ No trend data this scan. Will retry next cycle.")
        return

    spikes = detect_spikes(ranked, last_ranked)

    embed_data = format_report_embed(ranked, examples, reddit_scores, google_scores)
    embed = discord.Embed.from_dict(embed_data)
    await channel.send(embed=embed)

    if spikes:
        role_mention = f"<@&{ALERT_ROLE_ID}> " if ALERT_ROLE_ID else ""
        lines = [f"{role_mention}**⚡ SPIKE ALERT**\n"]
        for brand, jump, rating in spikes[:3]:
            lines.append(f"🔥 **{brand}** rocketed `{rating}/10` (↑{jump} spots)")
        lines.append("\n*Momentum shift — check prices now.*")
        await channel.send("\n".join(lines))

    last_ranked = ranked
    print(f"[OK] posted · ranked={len(ranked)} · spikes={len(spikes)}")


# ---------- DISCORD COMMANDS ----------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not auto_scan.is_running():
        auto_scan.start()
    await asyncio.sleep(8)
    try:
        await post_report()
    except Exception as e:
        print(f"[Boot error] {e}")


@tasks.loop(hours=CHECK_INTERVAL_HOURS)
async def auto_scan():
    try:
        await post_report()
    except Exception as e:
        print(f"[Auto scan error] {e}")


@auto_scan.before_loop
async def before_scan():
    await bot.wait_until_ready()


@bot.command(name="trends")
async def trends_cmd(ctx):
    """Manually trigger a trend scan."""
    await ctx.send("🔎 Scanning trends... (~20s)")
    try:
        await post_report()
    except Exception as e:
        await ctx.send(f"❌ `{e}`")


@bot.command(name="hot")
async def hot_cmd(ctx):
    """Show the top 3 brands right now."""
    if not last_ranked:
        await ctx.send("No data yet. Run `!trends` first.")
        return
    top_score = last_ranked[0][1] if last_ranked else 1
    lines = ["🔥 **Top 3 Right Now**"]
    for i, (brand, score) in enumerate(last_ranked[:3]):
        from trends import normalize_rating
        r = normalize_rating(score, top_score)
        lines.append(f"{i+1}. **{brand}** — `{r}/10`")
    await ctx.send("\n".join(lines))


@bot.command(name="price")
async def price_cmd(ctx, *, item: str):
    """Look up live StockX resale prices for any item. Usage: !price Jordan 1 Chicago"""
    if not APIFY_TOKEN:
        await ctx.send("⚠️ StockX API not configured. Add `APIFY_TOKEN` to Railway variables.")
        return

    await ctx.send(f"🔍 Checking StockX for **{item}**... (~30s)")

    results = await fetch_stockx_price(item)

    if not results:
        await ctx.send("❌ No results found. Try a more specific query like `!price Jordan 1 Retro High`.")
        return

    embed = discord.Embed(
        title=f"💸 StockX Resale: {item}",
        color=0x00FF7F
    )

    for product in results[:3]:
        name = product.get("title", product.get("name", "Unknown"))
        retail = product.get("retailPrice", "N/A")
        lowest_ask = product.get("lowestAsk", "N/A")
        highest_bid = product.get("highestBid", "N/A")
        last_sale = product.get("lastSale", "N/A")
        url = product.get("productUrl", "")

        # Calculate premium
        premium = "N/A"
        if isinstance(retail, (int, float)) and isinstance(lowest_ask, (int, float)) and retail > 0:
            pct = ((lowest_ask - retail) / retail) * 100
            premium = f"{pct:+.0f}%"

        value = (
            f"**Retail:** `${retail}`\n"
            f"**Lowest Ask:** `${lowest_ask}`\n"
            f"**Highest Bid:** `${highest_bid}`\n"
            f"**Last Sale:** `${last_sale}`\n"
            f"**Premium:** `{premium}`"
        )
        embed.add_field(name=name[:100], value=value, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


@bot.command(name="time")
async def time_cmd(ctx):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(TIMEZONE))
    await ctx.send(f"🕒 **{now.strftime('%A, %B %d, %Y — %I:%M %p')}** ({LOCATION_LABEL})")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)