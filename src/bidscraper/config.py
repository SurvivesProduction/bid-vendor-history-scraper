"""Generic environment-based configuration loading for bidscraper.

Loads variables from a `.env` file (if present) via python-dotenv, then
reads them from the process environment. This module intentionally knows
nothing about any specific client or hosting provider (e.g. Supabase) --
that kind of wiring belongs in a downstream "full" deployment package.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# NOTE: load_dotenv() with no path argument walks UP from THIS file's own
# directory (this installed package's location), not from the caller's
# directory or the process cwd. That means this call only ever finds a
# .env sitting in bidscraper's own source tree -- it does NOT find a
# downstream "full" deployment repo's .env, even though that's almost
# always where the real .env actually lives. Each entry point that needs
# real credentials (scripts/run_client.py, scripts/migrate.py in the
# "full" repos) must call load_dotenv() again, itself, from a file that
# actually lives inside that repo. Discovered the hard way in
# scripts/migrate.py (see that file's own "full" repo for the story) --
# don't remove downstream load_dotenv() calls that look "redundant" with
# this one; they're not.
load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    """Connection settings for the Postgres database.

    Prefers a single DATABASE_URL, falling back to the discrete PG*
    variables (the standard libpq environment variable names) when it
    isn't set.
    """

    dsn: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            return cls(dsn=database_url)

        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        dbname = os.environ.get("PGDATABASE")
        user = os.environ.get("PGUSER")
        password = os.environ.get("PGPASSWORD")

        if not dbname:
            raise RuntimeError(
                "No DATABASE_URL and no PGDATABASE set. Provide DATABASE_URL "
                "or the standard PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD "
                "environment variables."
            )

        auth = ""
        if user:
            auth = user
            if password:
                auth += f":{password}"
            auth += "@"

        dsn = f"postgresql://{auth}{host}:{port}/{dbname}"
        return cls(dsn=dsn)


def get_client_id(default: str | None = None) -> str | None:
    """Read CLIENT_ID from the environment.

    Returns `default` (None unless provided) when unset -- this package is
    client-agnostic, so no default client id is hardcoded here.
    """
    return os.environ.get("CLIENT_ID", default)
