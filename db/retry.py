"""Retry helper for Supabase operations with backoff and throttling."""

import time
import logging

logger = logging.getLogger(__name__)

# Delay between Supabase calls to avoid overwhelming free tier
REQUEST_DELAY = 0.3

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 2


def with_retry(fn, description="operation"):
    """Execute fn() with retry on transient errors (502, timeouts, connection errors).

    Waits REQUEST_DELAY before each attempt to throttle requests.
    On failure, retries with exponential backoff.
    """
    backoff = INITIAL_BACKOFF

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY)
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            is_transient = any(k in err_str for k in ["502", "503", "Bad gateway", "timeout", "ConnectionTerminated", "ConnectError"])

            if is_transient and attempt < MAX_RETRIES:
                logger.warning("%s failed (attempt %d/%d), retrying in %ds: %s", description, attempt, MAX_RETRIES, backoff, err_str[:120])
                time.sleep(backoff)
                backoff *= 2
                continue

            raise
