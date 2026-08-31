# bid-vendor-history-scraper

Public template: scrapes municipal bid-award history to show which vendors keep winning gov/school contracts and which are coming up for rebid or renewal.

This is the generic/free version -- no client-specific targets, normalization, or alerting. See the full build for a real client deployment.

## What this is

`bidscraper` is a small, reusable framework for turning "a government bid/award portal" into normalized rows in Postgres:

- a `BaseScraper` abstract class defining the `fetch -> parse -> normalize` pipeline every concrete scraper implements,
- a `BidAward` schema every scraper normalizes into,
- a Postgres client with a 3-tier dedup strategy (exact key, fuzzy-match merge, fuzzy-match flagged for review) so re-running a scraper doesn't create duplicate rows,
- a couple of generic, client-agnostic insight queries (e.g. vendor win counts).

It intentionally does not include any real scraping targets, client identifiers, or hosting-provider-specific wiring (e.g. Supabase). Those live in a paid/full deployment layer that installs this package as a dependency and adds the client-specific pieces on top -- see [bid-vendor-history-scraper-full](../bid-vendor-history-scraper-full).

## Install

Requires Python >=3.11 and a Postgres database.

```bash
pip install -e .
# or, with test dependencies:
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in your own values:

```bash
cp .env.example .env
```

`DATABASE_URL` is the preferred way to configure the connection; if it's unset, the standard `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` variables are used instead.

## Run migrations

```bash
python scripts/migrate.py
```

This applies every SQL file under `src/bidscraper/migrations/` (currently just `001_init_schema.sql`, which creates `bid_awards` and `digest_runs`) in order. Every migration is written with `if not exists` guards, so it's safe to rerun.

## Run the demo scraper

```bash
python scripts/run_scraper.py --client-id demo
```

This runs `ExampleStaticScraper` (in `scripts/run_scraper.py`), a template `BaseScraper` subclass that reads from a small hardcoded in-memory dataset -- not a real portal -- and upserts the results into `bid_awards`. It's meant to be a working, runnable demonstration of the full framework end to end, and a reference for what a real scraper's `fetch`/`parse`/`normalize` methods should look like.

## How the pieces fit together

This package defines the extension points a real deployment overlays:

- **`bidscraper.scrapers.base.BaseScraper`** -- subclass this once per portal type. `fetch()` retrieves raw content, `parse()` turns it into a list of raw record dicts, `normalize()` turns one raw record into a `BidAward`. `run()` orchestrates all three and yields `BidAward` instances.
- **`bidscraper.normalize.schema.BidAward`** -- the normalized shape every scraper must produce. It intentionally excludes dedup bookkeeping fields (`record_key`, `dedup_method`, `match_confidence`, `needs_review`) -- those are computed at insert time, not by the scraper.
- **`bidscraper.db.client.upsert_bid_award`** -- takes a `BidAward` and writes it to Postgres using the 3-tier dedup strategy:
  1. Exact match on `(client_id, source, record_key)` -- refreshes the existing row's content.
  2. No exact match, but a fuzzy match (`rapidfuzz` similarity on title + vendor, within a small award-date window) with confidence >= 0.90 -- merges into that row (`dedup_method='fuzzy_merge'`).
  3. Fuzzy match with confidence between 0.75 and 0.90 -- inserted as a new row flagged `needs_review=true` for a human to confirm.
  4. Otherwise -- inserted as a genuinely new row.
- **`bidscraper.insights.basic.vendor_win_counts`** -- a generic starting point for insight queries over the shared schema.

A downstream deployment (like the full/paid repo) adds concrete scraper subclasses for real portals, a client-specific config (`client_id`, targets), and any alerting/digest logic on top -- without needing to touch or fork this package's code.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Covers `compute_record_key` (native-id vs. hash paths), `BidAward` validation, and the fuzzy-match confidence banding logic (the pure scoring/classification functions are factored out of the DB query so they're testable without a live database).
