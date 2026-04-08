"""Slack weekly digest via incoming webhook, summarized by Claude Sonnet."""

import json
import os
import logging
from collections import Counter
from datetime import datetime, timezone
import anthropic
import httpx

logger = logging.getLogger(__name__)


def _build_stats_context(classified_rows: list[dict], game_config: dict) -> str:
    sections = []
    region_groups = game_config["sheet_region_groups"]

    for group_name, group_config in region_groups.items():
        group_regions = group_config["regions"]
        filtered = [
            r for r in classified_rows
            if r.get("feedback_raw", {}).get("region") in group_regions
        ]

        if not filtered:
            sections.append(f"{group_name}: No data this week")
            continue

        total = len(filtered)
        sentiment_counter = Counter(r.get("sentiment") for r in filtered)
        category_counter = Counter()
        for r in filtered:
            for cat in r.get("categories", []):
                category_counter[cat] += 1

        critical_items = [r for r in filtered if r.get("severity") == "critical"]

        section = f"{group_name} ({total} items):\n"
        section += f"  Sentiment: {dict(sentiment_counter)}\n"
        section += f"  Top categories: {category_counter.most_common(5)}\n"
        section += f"  Critical items: {len(critical_items)}\n"

        if critical_items:
            section += "  Critical details:\n"
            for item in critical_items[:5]:
                section += f"    - {item.get('summary', 'N/A')}\n"

        section += "  Sample feedback summaries:\n"
        for item in filtered[:20]:
            section += f"    - [{item.get('sentiment')}] {item.get('summary', 'N/A')}\n"

        sections.append(section)

    return "\n".join(sections)


def build_digest_message(classified_rows: list[dict], sheet_url: str, game_config: dict) -> str:
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%b %d, %Y")
    display_name = game_config["display_name"]
    game_desc = game_config["game_description"]

    stats_context = _build_stats_context(classified_rows, game_config)

    try:
        client = anthropic.Anthropic(max_retries=3)

        region_groups = game_config["sheet_region_groups"]
        region_instructions = "\n".join(
            f"- {name} Summary section with {cfg['flag']} flag: item count, top 3 issues with counts, "
            "sentiment percentages, critical items count with brief description, any notable trends"
            for name, cfg in region_groups.items()
        )

        response = client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Summarize this week's user feedback for {display_name} ({game_desc}) into a Slack digest.

Data for week of {week_str}:

{stats_context}

Format as a Slack message with:
- Header with week date
{region_instructions}
- Keep it concise but insightful \u2014 highlight what the team should pay attention to
- Use Slack markdown (*bold*, bullet points with \u2022)
- End with :link: <{sheet_url}|Full report>

Output ONLY the Slack message text, nothing else.""",
            }],
        )
        return response.content[0].text
    except Exception as e:
        logger.error("Sonnet digest generation failed, using fallback: %s", e)
        return _build_fallback_digest(classified_rows, sheet_url, week_str, game_config)


def _build_fallback_digest(classified_rows: list[dict], sheet_url: str,
                           week_str: str, game_config: dict) -> str:
    display_name = game_config["display_name"]
    region_groups = game_config["sheet_region_groups"]

    sections = [f"*{display_name} Feedback \u2014 Week of {week_str}*\n"]

    for group_name, group_config in region_groups.items():
        flag = group_config["flag"]
        group_regions = group_config["regions"]
        filtered = [r for r in classified_rows if r.get("feedback_raw", {}).get("region") in group_regions]

        if not filtered:
            sections.append(f"{flag} *{group_name} Summary:* No data this week\n")
            continue

        total = len(filtered)
        category_counter = Counter()
        for r in filtered:
            for cat in r.get("categories", []):
                category_counter[cat] += 1

        top_3 = ", ".join(f"{c} ({n})" for c, n in category_counter.most_common(3))
        critical = sum(1 for r in filtered if r.get("severity") == "critical")

        lines = [f"{flag} *{group_name} Summary ({total} items):*", f"\u2022 Top issues: {top_3}"]
        if critical:
            lines.append(f"\u2022 :red_circle: {critical} critical items")
        sections.append("\n".join(lines) + "\n")

    sections.append(f":link: <{sheet_url}|Full report>")
    return "\n".join(sections)


def post_slack_digest(
    message: str,
    webhook_url: str | None = None,
) -> None:
    url = webhook_url or os.environ["SLACK_WEBHOOK_URL"]

    response = httpx.post(url, json={"text": message}, timeout=30)

    if response.status_code != 200:
        logger.error("Slack webhook failed: %s %s", response.status_code, response.text)
        raise RuntimeError(f"Slack webhook failed: {response.status_code}")

    logger.info("Slack digest posted successfully")
