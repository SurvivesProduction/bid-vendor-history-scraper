-- 001_init_schema.sql
-- Initial schema for bidscraper: bid_awards + digest_runs.
-- Written to be safe to rerun (idempotent): every statement uses an
-- `if not exists` guard.

create extension if not exists pgcrypto;

create table if not exists bid_awards (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    source text not null,
    source_record_id text,
    record_key text not null,
    dedup_method text not null,
    match_confidence numeric,
    needs_review boolean not null default false,
    awarding_agency text,
    project_title text,
    project_description text,
    awarded_vendor text,
    award_date date,
    contract_value numeric,
    contract_term_end date,
    raw_data jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (client_id, source, record_key)
);

create index if not exists idx_bid_awards_client_vendor
    on bid_awards (client_id, awarded_vendor);

create index if not exists idx_bid_awards_client_term_end
    on bid_awards (client_id, contract_term_end);

create index if not exists idx_bid_awards_needs_review
    on bid_awards (needs_review)
    where needs_review;

create table if not exists digest_runs (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    run_at timestamptz not null default now(),
    new_records_count int not null default 0,
    rebid_alerts_count int not null default 0
);

create index if not exists idx_digest_runs_client_run_at
    on digest_runs (client_id, run_at desc);
