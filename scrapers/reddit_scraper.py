"""Reddit scraper for r/LivlyIsland using PRAW."""

import os
from datetime import datetime, timezone
from typing import Optional
import praw
from scrapers.base import FeedbackItem, ScraperResult

SUBREDDIT_NAME = "LivlyIsland"
REDDIT_BASE_URL = "https://reddit.com"


def _get_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent="livly-feedback-bot/1.0 (by /u/{})".format(
            os.environ.get("REDDIT_USERNAME", "livly-feedback")
        ),
    )


def _submission_to_feedback(submission) -> FeedbackItem:
    content = submission.title
    if submission.selftext:
        content += "\n\n" + submission.selftext

    posted_at = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)

    return FeedbackItem(
        source="reddit",
        region="en",
        external_id=f"post_{submission.id}",
        author=submission.author.name if submission.author else "[deleted]",
        content=content,
        rating=None,
        channel=f"r/{SUBREDDIT_NAME}",
        source_url=REDDIT_BASE_URL + submission.permalink,
        posted_at=posted_at,
    )


def _comment_to_feedback(comment) -> FeedbackItem:
    posted_at = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)

    return FeedbackItem(
        source="reddit",
        region="en",
        external_id=f"comment_{comment.id}",
        author=comment.author.name if comment.author else "[deleted]",
        content=comment.body,
        rating=None,
        channel=f"r/{SUBREDDIT_NAME}",
        source_url=REDDIT_BASE_URL + comment.permalink,
        posted_at=posted_at,
    )


def scrape_reddit(
    since: Optional[datetime] = None,
    post_limit: int = 100,
    comments_per_post: int = 20,
) -> list[ScraperResult]:
    items = []
    error = None

    try:
        reddit = _get_reddit_client()
        subreddit = reddit.subreddit(SUBREDDIT_NAME)

        for submission in subreddit.new(limit=post_limit):
            posted_at = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
            if since and posted_at < since:
                break

            items.append(_submission_to_feedback(submission))

            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:comments_per_post]:
                if not comment.body or comment.body == "[deleted]":
                    continue
                items.append(_comment_to_feedback(comment))
    except Exception as e:
        error = str(e)

    return [ScraperResult(source="reddit", region="en", items=items, error=error)]
