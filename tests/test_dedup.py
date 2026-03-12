from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from scrapers.base import FeedbackItem, compute_content_hash
from db.dedup import deduplicate_and_insert


def _make_item(external_id="rev-1", content="Great game!", rating=5):
    return FeedbackItem(
        source="appstore_ios",
        region="en",
        external_id=external_id,
        author="user1",
        content=content,
        rating=rating,
        channel=None,
        source_url=None,
        posted_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )


def test_new_item_is_inserted(mocker):
    """A feedback item with a new hash should be inserted."""
    mock_client = MagicMock()
    run_id = "run-001"

    # Both hash check and external_id check return empty
    hash_check_result = MagicMock()
    hash_check_result.data = []

    id_check_result = MagicMock()
    id_check_result.data = []

    insert_result = MagicMock()
    insert_result.data = [{"id": "new-uuid"}]

    select_call_count = {"n": 0}
    original_table = MagicMock()

    def select_side_effect(*args):
        select_call_count["n"] += 1
        mock_chain = MagicMock()
        if select_call_count["n"] == 1:
            mock_chain.eq.return_value.execute.return_value = hash_check_result
        else:
            mock_chain.eq.return_value.eq.return_value.is_.return_value.execute.return_value = id_check_result
        return mock_chain

    original_table.select = select_side_effect
    original_table.insert.return_value.execute.return_value = insert_result
    mock_client.table.return_value = original_table

    items = [_make_item()]
    result = deduplicate_and_insert(mock_client, items, run_id)

    assert result["inserted"] == 1
    assert result["skipped"] == 0
    assert result["updated"] == 0


def test_duplicate_item_is_skipped(mocker):
    """A feedback item with an existing hash should be skipped."""
    mock_client = MagicMock()
    run_id = "run-001"

    item = _make_item()
    h = compute_content_hash(item.source, item.external_id, item.content, item.rating)

    # Hash already exists
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"content_hash": h}
    ]

    result = deduplicate_and_insert(mock_client, [item], run_id)

    assert result["inserted"] == 0
    assert result["skipped"] == 1


def test_edited_item_supersedes_old(mocker):
    """Same external_id but different hash -> insert new, mark old as superseded."""
    mock_client = MagicMock()
    run_id = "run-001"

    item = _make_item(content="Updated review text")

    # Set up chained mock: hash check returns [] (no duplicate hash)
    hash_check_result = MagicMock()
    hash_check_result.data = []

    # external_id check returns existing row with different hash
    id_check_result = MagicMock()
    id_check_result.data = [{"id": "old-uuid", "content_hash": "different-hash"}]

    # insert returns new row
    insert_result = MagicMock()
    insert_result.data = [{"id": "new-uuid"}]

    # Track call order to return different results
    select_call_count = {"n": 0}
    original_table = MagicMock()

    def select_side_effect(*args):
        select_call_count["n"] += 1
        mock_chain = MagicMock()
        if select_call_count["n"] == 1:
            # First select: hash check
            mock_chain.eq.return_value.execute.return_value = hash_check_result
        else:
            # Second select: external_id check
            mock_chain.eq.return_value.eq.return_value.is_.return_value.execute.return_value = id_check_result
        return mock_chain

    original_table.select = select_side_effect
    original_table.insert.return_value.execute.return_value = insert_result
    original_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_client.table.return_value = original_table

    result = deduplicate_and_insert(mock_client, [item], run_id)

    assert result["inserted"] == 1
    assert result["updated"] == 1
