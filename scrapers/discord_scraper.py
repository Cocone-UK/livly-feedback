"""Discord channel message scraper using discord.py."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional
import discord
from scrapers.base import FeedbackItem, ScraperResult

TARGET_CHANNELS = [
    "app-bug-report",
    "app-feedback",
    "app-poll-feedback",
    "discord-feedback",
    "discord-poll-feedback",
    "livly-general",
    "gacha-chat",
    "q-and-a",
]


def _message_to_feedback(message: discord.Message) -> FeedbackItem:
    return FeedbackItem(
        source="discord",
        region="en",
        external_id=str(message.id),
        author=message.author.name,
        content=message.content,
        rating=None,
        channel=message.channel.name,
        source_url=message.jump_url,
        posted_at=message.created_at,
    )


async def _fetch_channel_messages(
    channel: discord.TextChannel,
    since: Optional[datetime],
    limit: int = 500,
) -> list[FeedbackItem]:
    items = []
    async for message in channel.history(after=since, limit=limit, oldest_first=False):
        if message.author.bot:
            continue
        if not message.content or not message.content.strip():
            continue
        items.append(_message_to_feedback(message))
    return items


async def _run_discord_scrape(
    since: Optional[datetime] = None,
) -> list[ScraperResult]:
    token = os.environ["DISCORD_BOT_TOKEN"]

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    results = []

    @client.event
    async def on_ready():
        try:
            all_items = []
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.name in TARGET_CHANNELS:
                        try:
                            items = await _fetch_channel_messages(channel, since)
                            all_items.extend(items)
                        except discord.Forbidden:
                            pass
                        except Exception as e:
                            results.append(ScraperResult(
                                source="discord",
                                region="en",
                                items=[],
                                error=f"Error in #{channel.name}: {e}",
                            ))

            results.append(ScraperResult(
                source="discord", region="en", items=all_items
            ))
        finally:
            await client.close()

    await client.start(token)
    return results


def scrape_discord(since: Optional[datetime] = None, game_config: dict | None = None) -> list[ScraperResult]:
    return asyncio.run(_run_discord_scrape(since))
