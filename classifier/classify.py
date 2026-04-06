"""AI classification pipeline using Claude Haiku 4.5 with tool-use."""

import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
import anthropic

logger = logging.getLogger(__name__)

CATEGORIES = [
    "ux",
    "tutorial_onboarding",
    "gacha_monetization",
    "social",
    "bugs_performance",
    "content_request",
    "account_login",
    "art_aesthetics",
    "general_praise",
    "events",
    "localization",
]

CLASSIFICATION_TOOL = {
    "name": "classify_feedback",
    "description": "Classify a piece of user feedback for Livly Island.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["positive", "negative", "neutral", "mixed"],
                "description": "Overall sentiment of the feedback.",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": CATEGORIES},
                "description": "One or more category tags.",
            },
            "severity": {
                "type": "string",
                "enum": ["critical", "moderate", "minor"],
                "description": "Critical = user churned/threatening to quit/data loss. Moderate = frustrated but playing. Minor = suggestion/cosmetic.",
            },
            "language": {
                "type": "string",
                "enum": ["en", "ja", "zh", "other"],
                "description": "Detected language of the feedback.",
            },
            "summary_en": {
                "type": "string",
                "description": "One-line summary in English.",
            },
            "summary_jp": {
                "type": "string",
                "description": "One-line summary in Japanese (for HQ).",
            },
            "key_quotes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Notable phrases extracted from the feedback.",
            },
        },
        "required": [
            "sentiment", "categories", "severity", "language",
            "summary_en", "summary_jp", "key_quotes",
        ],
    },
}

CONCURRENCY = 10  # parallel Anthropic API calls per batch


def _to_pg_array(items: list[str]) -> str:
    """Convert Python list to Postgres array literal."""
    escaped = []
    for item in items:
        s = item.replace("\\", "\\\\").replace('"', '\\"')
        escaped.append(f'"{s}"')
    return "{" + ",".join(escaped) + "}"


SYSTEM_PROMPT = """You are classifying user feedback for Livly Island, a mobile pet game by Cocone.
Analyze the feedback and classify it using the classify_feedback tool.

Severity guidelines:
- critical: User churned, threatening to quit, data loss, account locked out
- moderate: Frustrated but still playing, repeated complaint, functional issue
- minor: Suggestion, mild annoyance, cosmetic issue"""


def classify_feedback(
    client: anthropic.Anthropic,
    feedback_id: str,
    content: str,
    source: str,
    rating: Optional[int],
) -> Optional[dict]:
    """Classify a single feedback item using Claude Haiku 4.5.

    Returns classification dict or None if classification fails.
    """

    rating_str = f"{rating}/5" if rating is not None else "N/A"
    user_message = f"Feedback from {source} (rating: {rating_str}):\n\n{content}"

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[CLASSIFICATION_TOOL],
            tool_choice={"type": "tool", "name": "classify_feedback"},
            messages=[{"role": "user", "content": user_message}],
        )

        for block in response.content:
            if block.type == "tool_use":
                result = block.input
                result["model_used"] = response.model
                result["feedback_id"] = feedback_id
                return result

        logger.error("No tool_use block in response for feedback %s", feedback_id)
        return None

    except Exception as e:
        logger.error("Classification failed for feedback %s: %s", feedback_id, e)
        return None


def _fetch_unclassified(supabase_client, batch_size: int) -> list[dict]:
    """Fetch unclassified, non-superseded feedback via Postgres RPC."""
    from db.retry import with_retry

    resp = with_retry(
        lambda: supabase_client.rpc(
            "unclassified_feedback", {"batch_limit": batch_size}
        ).execute(),
        "fetch unclassified feedback",
    )
    return resp.data or []


def classify_batch(
    supabase_client,
    batch_size: int = 200,
) -> dict:
    """Classify all unclassified, non-superseded feedback items.

    Uses parallel API calls (ThreadPoolExecutor) for throughput.
    Loops in batches until no unclassified items remain.
    Returns dict with counts: classified, failed.
    """
    from db.retry import with_retry

    ai_client = anthropic.Anthropic(max_retries=3)
    classified_count = 0
    failed_count = 0

    while True:
        batch = _fetch_unclassified(supabase_client, batch_size)
        if not batch:
            break

        logger.info("Classifying batch of %d items", len(batch))

        # Parallel classify via thread pool
        results: list[tuple[dict, Optional[dict]]] = []
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            futures = {
                executor.submit(
                    classify_feedback, ai_client,
                    row["id"], row["content"], row["source"], row.get("rating"),
                ): row
                for row in batch
            }
            for future in as_completed(futures):
                results.append((futures[future], future.result()))

        # Sequential DB inserts
        for row, result in results:
            if result is None:
                failed_count += 1
                continue

            insert_data = {
                "feedback_id": result["feedback_id"],
                "sentiment": result["sentiment"],
                "categories": _to_pg_array(result.get("categories", [])),
                "severity": result["severity"],
                "language": result["language"],
                "summary": result["summary_en"],
                "summary_jp": result["summary_jp"],
                "key_quotes": _to_pg_array(result.get("key_quotes", [])),
                "model_used": result["model_used"],
            }
            with_retry(
                lambda d=insert_data: supabase_client.table("feedback_classified").insert(d).execute(),
                "insert classification",
            )

            classified_count += 1

    return {"classified": classified_count, "failed": failed_count}
