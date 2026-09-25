@bot.command(name="trends")
async def trends_cmd(ctx):
    """Manually trigger a trend scan."""
    msg = await ctx.send("```\n● SCANNING LIVE MARKET…\nTikTok · StockX · Grailed\n```")
    try:
        ranked, extra, sources_ok = await build_trend_report()

        if not ranked:
            await msg.edit(content=(
                "⚠ **INSUFFICIENT LIVE DATA**\n"
                "Not enough verified market data was available to generate a report.\n"
                "Try again in a few minutes."
            ))
            return

        embed_data = format_report_embed(ranked, extra, sources_ok)
        await msg.edit(content=None, embed=discord.Embed.from_dict(embed_data))

        if ALERT_ROLE_ID:
            await ctx.send(f"<@&{ALERT_ROLE_ID}> scan complete")

    except Exception as e:
        await msg.edit(content=f"❌ Scan failed: `{e}`")
