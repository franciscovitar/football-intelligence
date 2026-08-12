\set ON_ERROR_STOP on

begin;

create schema if not exists perception;

revoke all on schema perception from public;

insert into ingestion.providers (code, display_name)
values ('perception-web', 'Perception Web Feeds')
on conflict (code) do update
set
    display_name = excluded.display_name,
    is_active = true;

create table perception.sources (
    id bigint generated always as identity primary key,
    code text not null unique,
    display_name text not null,
    source_kind text not null,
    homepage_url text,
    feed_url text not null unique,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint perception_sources_code_format_check
        check (code ~ '^[a-z0-9][a-z0-9-]*$'),
    constraint perception_sources_display_name_not_blank_check
        check (btrim(display_name) <> ''),
    constraint perception_sources_kind_check
        check (source_kind in ('expert', 'media', 'fan', 'other')),
    constraint perception_sources_homepage_url_check
        check (homepage_url is null or homepage_url ~ '^https?://'),
    constraint perception_sources_feed_https_check
        check (feed_url ~ '^https://')
);

create index perception_sources_active_kind_idx
    on perception.sources (is_active, source_kind, code);

create table perception.evidence_items (
    id bigint generated always as identity primary key,
    source_id bigint not null
        references perception.sources(id) on delete restrict,
    external_id text,
    canonical_url text not null,
    title text not null,
    excerpt text,
    published_at timestamptz,
    discovered_at timestamptz not null default now(),
    content_sha256 text not null,
    duplicate_of_id bigint
        references perception.evidence_items(id) on delete set null,
    raw_metadata jsonb not null default '{}'::jsonb,
    ingestion_version text not null,
    constraint perception_evidence_external_id_not_blank_check
        check (external_id is null or btrim(external_id) <> ''),
    constraint perception_evidence_url_check
        check (canonical_url ~ '^https?://'),
    constraint perception_evidence_title_not_blank_check
        check (btrim(title) <> ''),
    constraint perception_evidence_excerpt_not_blank_check
        check (excerpt is null or btrim(excerpt) <> ''),
    constraint perception_evidence_sha256_check
        check (content_sha256 ~ '^[0-9a-f]{64}$'),
    constraint perception_evidence_not_self_duplicate_check
        check (duplicate_of_id is null or duplicate_of_id <> id),
    constraint perception_evidence_metadata_object_check
        check (jsonb_typeof(raw_metadata) = 'object'),
    constraint perception_evidence_ingestion_version_not_blank_check
        check (btrim(ingestion_version) <> ''),
    constraint perception_evidence_source_url_key
        unique (source_id, canonical_url)
);

create unique index perception_evidence_source_external_idx
    on perception.evidence_items (source_id, external_id)
    where external_id is not null;

create index perception_evidence_published_idx
    on perception.evidence_items (published_at desc nulls last, discovered_at desc);

create index perception_evidence_content_hash_idx
    on perception.evidence_items (content_sha256, duplicate_of_id);

create index perception_evidence_source_published_idx
    on perception.evidence_items (source_id, published_at desc nulls last);

create table perception.player_evidence_mentions (
    evidence_id bigint not null
        references perception.evidence_items(id) on delete cascade,
    player_id bigint not null
        references football.players(id) on delete cascade,
    matched_text text not null,
    match_method text not null,
    context_excerpt text,
    created_at timestamptz not null default now(),
    primary key (evidence_id, player_id),
    constraint perception_mentions_matched_text_not_blank_check
        check (btrim(matched_text) <> ''),
    constraint perception_mentions_match_method_check
        check (match_method in ('display_name_exact', 'manual')),
    constraint perception_mentions_context_not_blank_check
        check (context_excerpt is null or btrim(context_excerpt) <> '')
);

create index perception_mentions_player_evidence_idx
    on perception.player_evidence_mentions (player_id, evidence_id);

revoke all on all tables in schema perception from public;

commit;
