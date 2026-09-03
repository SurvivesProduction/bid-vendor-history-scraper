-- 002_vendor_aliases.sql
-- Vendor-name canonicalization: the same real-world vendor often shows up
-- under several spellings across different source documents (e.g.
-- "CT Electric Corp", "CT Electric Corp.", "CT Electrical Corp",
-- "C. T. Electrical Corp" are all the same company). vendor_aliases maps
-- each raw awarded_vendor spelling seen for a client to one canonical
-- name, so insight queries (vendor_win_counts) can group by real-world
-- identity instead of exact string. Written to be safe to rerun.

create table if not exists vendor_aliases (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    raw_name text not null,
    canonical_name text not null,
    match_method text not null,
    confidence numeric,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (client_id, raw_name)
);

create index if not exists idx_vendor_aliases_client_canonical
    on vendor_aliases (client_id, canonical_name);
