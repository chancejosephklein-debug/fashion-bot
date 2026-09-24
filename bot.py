import discord
from discord.ext import commands
import aiohttp

from config import DISCORD_TOKEN, ALERT_ROLE_ID
from trends import build_trend_report, format_report_embed, get_stockx_prices, get_grailed_sold

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
        stockx_lines = []
        for p in stockx[:3]:
            name = (p.get("title") or p.get("name") or "Unknown")[:80]
            ask = p.get("lowestAsk") or p.get("price") or "?"
            stockx_lines.append(f"**{name}**\n  Lowest Ask: `${ask}`")
        embed.add_field(name="💸 StockX", value="\n\n".join(stockx_lines), inline=False)
    
    if grailed:
        grailed_lines = []
        for g in grailed[:3]:
            name = (g.get("title") or g.get("name") or "Unknown")[:80]
            sold = g.get("soldPrice") or g.get("price") or "?"
            grailed_lines.append(f"**{name}**\n  Sold: `${sold}`")
        embed.add_field(name="📊 Grailed (Sold)", value="\n\n".join(grailed_lines), inline=False)
    
    if not stockx and not grailed:
        embed.description = "No results found. Try a different search."
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
