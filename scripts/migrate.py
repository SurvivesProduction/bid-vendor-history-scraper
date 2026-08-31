#!/usr/bin/env python
"""CLI entry point: run bidscraper's SQL migrations against DATABASE_URL.

Usage:
    python scripts/migrate.py
"""
from __future__ import annotations

import sys

from bidscraper.migrate import main

if __name__ == "__main__":
    sys.exit(main())
