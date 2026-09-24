import discord
from discord.ext import commands
import aiohttp

from config import DISCORD_TOKEN, ALERT_ROLE_ID
from trends import build_trend_report, format_report_embed

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("Bot is ready. Run !trends to scan.")


@bot.command(name="trends")
async def trends_cmd(ctx):
    msg = await ctx.send("🔎 Scanning TikTok + StockX + Grailed... (~60s)")
    try:
        ranked, examples, price_data = await build_trend_report()
        if not ranked:
            await msg.edit(content="❌ No trend data. Check APIFY_TOKEN.")
            return
        embed_data = format_report_embed(ranked, examples, price_data)
        await msg.edit(content=None, embed=discord.Embed.from_dict(embed_data))
        if ALERT_ROLE_ID:
            await ctx.send(f"<@&{ALERT_ROLE_ID}> scan complete")
    except Exception as e:
        await msg.edit(content=f"❌ `{e}`")


@bot.command(name="price")
async def price_cmd(ctx, *, item: str):
    from trends import get_stockx_prices, get_grailed_sold
    msg = await ctx.send(f"🔍 Checking prices for **{item}**...")
    async with aiohttp.ClientSession() as session:
        stockx = await get_stockx_prices(session, item)
        grailed = await get_grailed_sold(session, item)

    embed = discord.Embed(title=f"💸 {item}", color=0x00FF7F)
    if stockx:
        for p in stockx[:3]:
            name = (p.get("title") or p.get("name") or "Unknown")[:80]
            ask = p.get("lowestAsk") or p.get("price") or "?"
            embed.add_field(name=f"StockX: {name}", value=f"Lowest Ask: `${ask}`", inline=False)
    if grailed:
        for g in grailed[:3]:
            name = (g.get("title") or g.get("name") or "Unknown")[:80]
            sold = g.get("soldPrice") or g.get("price") or "?"
            embed.add_field(name=f"Grailed Sold: {name}", value=f"Price: `${sold}`", inline=False)
    if not stockx and not grailed:
        embed.description = "No results found."
    await msg.edit(content=None, embed=embed)


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
