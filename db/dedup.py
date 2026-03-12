"""Deduplication logic for feedback items."""

from scrapers.base import FeedbackItem, compute_content_hash
from supabase import Client


def deduplicate_and_insert(
    client: Client,
    items: list[FeedbackItem],
    run_id: str,
) -> dict:
    """Insert feedback items with SHA-256 dedup.

    Returns dict with counts: inserted, skipped, updated.
    """
    inserted = 0
    skipped = 0
    updated = 0

    for item in items:
        content_hash = compute_content_hash(
            item.source, item.external_id, item.content, item.rating
        )

        # Check if exact hash already exists (duplicate)
        existing_hash = (
            client.table("feedback_raw")
            .select("content_hash")
            .eq("content_hash", content_hash)
            .execute()
        )
        if existing_hash.data:
            skipped += 1
            continue

        # Check if same source+external_id exists with different hash (edit)
        existing_by_id = (
            client.table("feedback_raw")
            .select("id, content_hash")
            .eq("source", item.source)
            .eq("external_id", item.external_id)
            .is_("superseded_by", "null")
            .execute()
        )

        row = {
            "content_hash": content_hash,
            "source": item.source,
            "region": item.region,
            "external_id": item.external_id,
            "author": item.author,
            "content": item.content,
            "rating": item.rating,
            "channel": item.channel,
            "source_url": item.source_url,
            "posted_at": item.posted_at.isoformat(),
            "scrape_run_id": run_id,
        }

        new_row = client.table("feedback_raw").insert(row).execute()
        new_id = new_row.data[0]["id"]
        inserted += 1

        # If there was an old version, mark it as superseded
        if existing_by_id.data:
            old_id = existing_by_id.data[0]["id"]
            client.table("feedback_raw").update(
                {"superseded_by": new_id}
            ).eq("id", old_id).execute()
            updated += 1

    return {"inserted": inserted, "skipped": skipped, "updated": updated}
