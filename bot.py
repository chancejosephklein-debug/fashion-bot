import discord
from discord.ext import commands, tasks
import asyncio

from config import (
    DISCORD_TOKEN, TREND_CHANNEL_ID, ALERT_ROLE_ID, CHECK_INTERVAL_HOURS
)
from trends import build_trend_report, format_report, detect_spikes

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
    spikes = detect_spikes(ranked, last_ranked)

    report = format_report(ranked, examples, reddit_scores, google_scores)
    await channel.send(report)

    if spikes:
        role_mention = f"<@&{ALERT_ROLE_ID}> " if ALERT_ROLE_ID else ""
        spike_lines = [f"{role_mention}**⚡ TREND SPIKE DETECTED**\n"]
        for brand, jump, score in spikes:
            spike_lines.append(f"• **{brand}** jumped **{jump} spots** → score `{score:.0f}` 🚨")
        spike_lines.append("\n*Move fast — spikes often precede resale price bumps.*")
        await channel.send("\n".join(spike_lines))

    last_ranked = ranked
    print(f"[OK] Report posted with {len(spikes)} spikes")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not auto_scan.is_running():
        auto_scan.start()
    await asyncio.sleep(10)
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
    await ctx.send("🔎 Scanning fashion trends... (~20s)")
    try:
        await post_report()
    except Exception as e:
        await ctx.send(f"❌ Error: `{e}`")


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)