"""Supabase client singleton."""

import os
from supabase import create_client, Client


def get_supabase_client() -> Client:
    """Create and return a Supabase client from environment variables."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)
