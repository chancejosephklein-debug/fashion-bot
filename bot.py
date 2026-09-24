import discord
from discord.ext import commands, tasks
import asyncio

from config import (
    DISCORD_TOKEN, TREND_CHANNEL_ID, ALERT_ROLE_ID, CHECK_INTERVAL_HOURS
)
from trends import (
    build_trend_report, format_report_embed, detect_spikes,
)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
last_ranked = []


async def post_report():
    global last_ranked
    channel = bot.get_channel(TREND_CHANNEL_ID)
    if not channel:
        print(f"[ERR] Channel {TREND_CHANNEL_ID} not found")
        return

    ranked, examples, reddit_scores, google_scores = await build_trend_report()

    if not ranked:
        await channel.send("⚠️ No trend data this scan — Reddit may be rate-limiting. Will retry next cycle.")
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
    await ctx.send("🔎 Scanning... (~20s)")
    try:
        await post_report()
    except Exception as e:
        await ctx.send(f"❌ `{e}`")


@bot.command(name="time")
async def time_cmd(ctx):
    from config import TIMEZONE, LOCATION_LABEL
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(TIMEZONE))
    await ctx.send(f"🕒 **{now.strftime('%A, %B %d, %Y — %I:%M %p')}** ({LOCATION_LABEL})")


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)