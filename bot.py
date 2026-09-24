import discord
from discord.ext import commands, tasks
import asyncio

from config import (
    DISCORD_TOKEN, TREND_CHANNEL_ID, ALERT_ROLE_ID, CHECK_INTERVAL_HOURS
)
from trends import (
    build_trend_report, format_report_embed, detect_spikes,
    normalize_rating, get_local_time,
)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
last_ranked = []
last_discovered = []


async def post_report():
    global last_ranked, last_discovered
    channel = bot.get_channel(TREND_CHANNEL_ID)
    if not channel:
        print(f"[ERR] Channel {TREND_CHANNEL_ID} not found")
        return

    ranked, examples, reddit_scores, google_scores, fresh = await build_trend_report(last_discovered)
    spikes = detect_spikes(ranked, last_ranked)

    embed_data = format_report_embed(ranked, examples, fresh)
    embed = discord.Embed.from_dict(embed_data)
    await channel.send(embed=embed)

    if spikes:
        role_mention = f"<@&{ALERT_ROLE_ID}> " if ALERT_ROLE_ID else ""
        top_score = ranked[0][1] if ranked else 1
        spike_lines = [f"{role_mention}**⚡ TREND SPIKE ALERT**\n"]
        for brand, jump, score in spikes[:6]:
            rating = normalize_rating(score, top_score)
            spike_lines.append(f"• **{brand}** jumped **{jump} spots** → now `{rating}/10` 🚨")
        spike_lines.append("\n*Move fast — spikes usually mean resale prices are about to move.*")
        await channel.send("\n".join(spike_lines))

    last_ranked = ranked
    last_discovered = list(set(last_discovered + fresh))[:50]
    print(f"[OK] Report posted · spikes={len(spikes)} · discovered={len(fresh)}")


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
    await ctx.send("🔎 Scanning trends... (~20s)")
    try:
        await post_report()
    except Exception as e:
        await ctx.send(f"❌ Error: `{e}`")


@bot.command(name="time")
async def time_cmd(ctx):
    now = get_local_time()
    await ctx.send(f"🕒 **{now.strftime('%A, %B %d, %Y — %I:%M %p')}** (Yuba City, CA)")


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send("🏓 Pong!")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)