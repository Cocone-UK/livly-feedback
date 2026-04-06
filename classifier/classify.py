"""AI classification pipeline using Claude Haiku 4.5 via Message Batches API."""

import logging
import time
from typing import Optional
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

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

POLL_INTERVAL = 30  # seconds between batch status checks


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


def classify_batch(supabase_client) -> dict:
    """Classify all unclassified feedback via the Anthropic Message Batches API.

    Submits all items in a single batch, polls for completion, then upserts results.
    50% cheaper and no timeout issues compared to sequential API calls.
    Returns dict with counts: classified, failed.
    """
    from db.retry import with_retry

    # Fetch all unclassified items in one shot
    all_unclassified = _fetch_unclassified(supabase_client, 10000)
    if not all_unclassified:
        logger.info("No unclassified items found")
        return {"classified": 0, "failed": 0}

    logger.info("Submitting %d items to Anthropic Batches API", len(all_unclassified))

    # Build batch requests
    requests = []
    for row in all_unclassified:
        rating_str = f"{row.get('rating')}/5" if row.get("rating") is not None else "N/A"
        user_message = f"Feedback from {row['source']} (rating: {rating_str}):\n\n{row['content']}"

        requests.append(Request(
            custom_id=str(row["id"]),
            params=MessageCreateParamsNonStreaming(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[CLASSIFICATION_TOOL],
                tool_choice={"type": "tool", "name": "classify_feedback"},
                messages=[{"role": "user", "content": user_message}],
            ),
        ))

    # Submit batch
    ai_client = anthropic.Anthropic()
    message_batch = ai_client.messages.batches.create(requests=requests)
    logger.info("Batch %s created (%d requests), polling...", message_batch.id, len(requests))

    # Poll until complete
    while message_batch.processing_status != "ended":
        time.sleep(POLL_INTERVAL)
        message_batch = ai_client.messages.batches.retrieve(message_batch.id)
        counts = message_batch.request_counts
        logger.info("Batch %s: %d processing, %d succeeded, %d errored",
                     message_batch.id, counts.processing, counts.succeeded, counts.errored)

    logger.info("Batch %s complete: %d succeeded, %d errored, %d expired",
                 message_batch.id, message_batch.request_counts.succeeded,
                 message_batch.request_counts.errored, message_batch.request_counts.expired)

    # Process results
    classified_count = 0
    failed_count = 0

    for result in ai_client.messages.batches.results(message_batch.id):
        if result.result.type != "succeeded":
            logger.error("Batch item %s: %s", result.custom_id, result.result.type)
            failed_count += 1
            continue

        message = result.result.message
        classification = None
        for block in message.content:
            if block.type == "tool_use":
                classification = block.input
                break

        if classification is None:
            logger.error("No tool_use in batch result for %s", result.custom_id)
            failed_count += 1
            continue

        insert_data = {
            "feedback_id": result.custom_id,
            "sentiment": classification["sentiment"],
            "categories": _to_pg_array(classification.get("categories", [])),
            "severity": classification["severity"],
            "language": classification["language"],
            "summary": classification["summary_en"],
            "summary_jp": classification["summary_jp"],
            "key_quotes": _to_pg_array(classification.get("key_quotes", [])),
            "model_used": message.model,
        }
        with_retry(
            lambda d=insert_data: supabase_client.table("feedback_classified").upsert(d).execute(),
            "upsert classification",
        )
        classified_count += 1

    return {"classified": classified_count, "failed": failed_count}
