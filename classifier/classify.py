"""AI classification pipeline using Claude Haiku 4.5 with tool-use."""

import os
import logging
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
                "enum": ["en", "ja", "other"],
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

SYSTEM_PROMPT = """You are classifying user feedback for Livly Island, a mobile pet game by Cocone.
Analyze the feedback and classify it using the classify_feedback tool.

Severity guidelines:
- critical: User churned, threatening to quit, data loss, account locked out
- moderate: Frustrated but still playing, repeated complaint, functional issue
- minor: Suggestion, mild annoyance, cosmetic issue"""


def classify_feedback(
    feedback_id: str,
    content: str,
    source: str,
    rating: Optional[int],
) -> Optional[dict]:
    """Classify a single feedback item using Claude Haiku 4.5.

    Returns classification dict or None if classification fails.
    """
    client = anthropic.Anthropic(max_retries=3)

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
    """Fetch unclassified, non-superseded feedback items."""
    classified_resp = (
        supabase_client.table("feedback_classified")
        .select("feedback_id")
        .limit(10000)
        .execute()
    )
    classified_ids = [r["feedback_id"] for r in (classified_resp.data or [])]

    query = (
        supabase_client.table("feedback_raw")
        .select("id, content, source, rating")
        .is_("superseded_by", "null")
        .limit(batch_size)
    )

    if classified_ids:
        query = query.not_.in_("id", classified_ids)

    return query.execute().data or []


def classify_batch(
    supabase_client,
    batch_size: int = 50,
) -> dict:
    """Classify all unclassified, non-superseded feedback items.

    Loops in batches of batch_size until no unclassified items remain.
    Returns dict with counts: classified, failed.
    """
    classified_count = 0
    failed_count = 0

    while True:
        batch = _fetch_unclassified(supabase_client, batch_size)
        if not batch:
            break

        for row in batch:
            result = classify_feedback(
                feedback_id=row["id"],
                content=row["content"],
                source=row["source"],
                rating=row.get("rating"),
            )

            if result is None:
                failed_count += 1
                continue

            supabase_client.table("feedback_classified").insert({
                "feedback_id": result["feedback_id"],
                "sentiment": result["sentiment"],
                "categories": result["categories"],
                "severity": result["severity"],
                "language": result["language"],
                "summary": result["summary_en"],
                "summary_jp": result["summary_jp"],
                "key_quotes": result["key_quotes"],
                "model_used": result["model_used"],
            }).execute()

            classified_count += 1

    return {"classified": classified_count, "failed": failed_count}
