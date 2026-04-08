"""Deduplication logic for feedback items."""

from scrapers.base import FeedbackItem, compute_content_hash
from supabase import Client
from db.retry import with_retry

BATCH_SIZE = 100  # chunk size for IN queries and inserts


def deduplicate_and_insert(
    client: Client,
    items: list[FeedbackItem],
    run_id: str,
    table_name: str = "feedback_raw",
) -> dict:
    """Insert feedback items with SHA-256 dedup.

    Batches hash lookups, id lookups, and inserts into chunked queries to
    avoid N sequential round-trips (one per item).

    Returns dict with counts: inserted, skipped, updated.
    """
    if not items:
        return {"inserted": 0, "skipped": 0, "updated": 0}

    # 1) Compute hashes and drop duplicates within this batch itself
    seen: set[str] = set()
    hashed_items: list[tuple[str, FeedbackItem]] = []
    for item in items:
        h = compute_content_hash(item.source, item.external_id, item.content, item.rating)
        if h in seen:
            continue
        seen.add(h)
        hashed_items.append((h, item))

    # 2) Batch-fetch existing hashes
    existing_hashes: set[str] = set()
    all_hashes = [h for h, _ in hashed_items]
    for i in range(0, len(all_hashes), BATCH_SIZE):
        chunk = all_hashes[i:i + BATCH_SIZE]
        resp = with_retry(
            lambda c=chunk: client.table(table_name)
            .select("content_hash")
            .in_("content_hash", c)
            .execute(),
            "dedup batch hash check",
        )
        for row in resp.data or []:
            existing_hashes.add(row["content_hash"])

    # 3) Filter out duplicates
    new_items = [(h, item) for h, item in hashed_items if h not in existing_hashes]
    skipped = len(hashed_items) - len(new_items)

    if not new_items:
        return {"inserted": 0, "skipped": skipped, "updated": 0}

    # 4) For each source, batch-fetch existing non-superseded (external_id -> id) to detect edits
    by_source: dict[str, list[FeedbackItem]] = {}
    for _, item in new_items:
        by_source.setdefault(item.source, []).append(item)

    existing_by_key: dict[tuple[str, str], str] = {}  # (source, external_id) -> old_id
    for source, source_items in by_source.items():
        external_ids = list({i.external_id for i in source_items})
        for i in range(0, len(external_ids), BATCH_SIZE):
            chunk = external_ids[i:i + BATCH_SIZE]
            resp = with_retry(
                lambda s=source, c=chunk: client.table(table_name)
                .select("id, external_id")
                .eq("source", s)
                .in_("external_id", c)
                .is_("superseded_by", "null")
                .execute(),
                "dedup batch id check",
            )
            for row in resp.data or []:
                existing_by_key[(source, row["external_id"])] = row["id"]

    # 5) Prepare and batch-insert new rows
    inserts = [
        {
            "content_hash": h,
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
        for h, item in new_items
    ]

    inserted_rows: list[dict] = []
    for i in range(0, len(inserts), BATCH_SIZE):
        chunk = inserts[i:i + BATCH_SIZE]
        resp = with_retry(
            lambda c=chunk: client.table(table_name).insert(c).execute(),
            "dedup batch insert",
        )
        inserted_rows.extend(resp.data or [])

    inserted = len(inserted_rows)

    # 6) Mark old versions as superseded where (source, external_id) already existed.
    # Supersedes are rare (only on user edits), so individual updates are fine here.
    new_by_key: dict[tuple[str, str], str] = {
        (row["source"], row["external_id"]): row["id"] for row in inserted_rows
    }
    updated = 0
    for key, old_id in existing_by_key.items():
        new_id = new_by_key.get(key)
        if not new_id:
            continue
        with_retry(
            lambda oid=old_id, nid=new_id: client.table(table_name)
            .update({"superseded_by": nid})
            .eq("id", oid)
            .execute(),
            "dedup supersede",
        )
        updated += 1

    return {"inserted": inserted, "skipped": skipped, "updated": updated}
