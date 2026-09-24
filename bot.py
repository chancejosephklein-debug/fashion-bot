import discord
from discord.ext import commands
import aiohttp
import os
from aiohttp import web

from config import DISCORD_TOKEN, ALERT_ROLE_ID
from trends import (
    build_trend_report, format_report_embed,
    get_stockx_prices, get_grailed_sold,
)

API_KEY = os.getenv("API_KEY", "")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------- WEB API (for Lovable site) ----------

async def trends_api(request):
    """Endpoint the website calls to get trend data."""
    provided = request.headers.get("X-API-Key") or request.query.get("key")
    if API_KEY and provided != API_KEY:
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        ranked, examples, price_data = await build_trend_report()
        data = []
        for brand, score in ranked[:10]:
            prices = price_data.get(brand, {})
            stockx = prices.get("stockx", [])
            grailed = prices.get("grailed", [])
            data.append({
                "brand": brand,
                "score": score,
                "stockx_ask": (stockx[0].get("lowestAsk") or stockx[0].get("price")) if stockx else None,
                "grailed_sold": (grailed[0].get("soldPrice") or grailed[0].get("price")) if grailed else None,
            })
        return web.json_response({"trends": data, "ok": True})
    except Exception as e:
        print(f"[API] error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def health_api(request):
    """Simple health check endpoint."""
    return web.json_response({"status": "ok", "bot": str(bot.user)})


async def start_web_server():
    app = web.Application()
    app.router.add_get("/api/trends", trends_api)
    app.router.add_get("/health", health_api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 Web API started on port 8080")


# ---------- DISCORD EVENTS ----------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("Bot is ready. Run !trends to scan.")
    if not hasattr(bot, "_api_started"):
        bot._api_started = True
        bot.loop.create_task(start_web_server())


# ---------- COMMANDS ----------

@bot.command(name="trends")
async def trends_cmd(ctx):
    """Manually trigger a trend scan."""
    msg = await ctx.send("🔎 Scanning TikTok + StockX + Grailed... (~60s)")
    try:
        ranked, examples, price_data = await build_trend_report()
        if not ranked:
            await msg.edit(content="❌ No trend data found. Check APIFY_TOKEN and Apify credits.")
            return
        embed_data = format_report_embed(ranked, examples, price_data)
        await msg.edit(content=None, embed=discord.Embed.from_dict(embed_data))
        if ALERT_ROLE_ID:
            await ctx.send(f"<@&{ALERT_ROLE_ID}> scan complete")
    except Exception as e:
        await msg.edit(content=f"❌ An error occurred: `{e}`")


@bot.command(name="price")
async def price_cmd(ctx, *, item: str):
    """Quick price lookup. Usage: !price Hellstar hoodie"""
    msg = await ctx.send(f"🔍 Checking prices for **{item}**...")
    async with aiohttp.ClientSession() as session:
        stockx = await get_stockx_prices(session, item)
        grailed = await get_grailed_sold(session, item)

    embed = discord.Embed(title=f"💸 Price Check: {item}", color=0x00FF7F)

    if stockx:
        lines = []
        for p in stockx[:3]:
            name = (p.get("title") or p.get("name") or "Unknown")[:80]
            ask = p.get("lowestAsk") or p.get("price") or "?"
            lines.append(f"**{name}**\n  Lowest Ask: `${ask}`")
        embed.add_field(name="💸 StockX", value="\n\n".join(lines), inline=False)

    if grailed:
        lines = []
        for g in grailed[:3]:
            name = (g.get("title") or g.get("name") or "Unknown")[:80]
            sold = g.get("soldPrice") or g.get("price") or "?"
            lines.append(f"**{name}**\n  Sold: `${sold}`")
        embed.add_field(name="📊 Grailed (Sold)", value="\n\n".join(lines), inline=False)

    if not stockx and not grailed:
        embed.description = "No results found. Try a different search."

    await msg.edit(content=None, embed=embed)


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
