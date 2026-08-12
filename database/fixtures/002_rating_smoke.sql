\set ON_ERROR_STOP on

do $$
declare
    player_id_value bigint;
    source_one_id bigint;
    source_two_id bigint;
    evidence_id_value bigint;
begin
    select id into player_id_value
    from football.players
    where display_name = 'Web Smoke Forward'
    order by id desc
    limit 1;

    if player_id_value is null then
        raise exception 'Web Smoke Forward fixture must run first';
    end if;

    select id into source_one_id
    from perception.sources
    where code = 'web-smoke-media';

    if source_one_id is null then
        raise exception 'web-smoke-media source fixture must run first';
    end if;

    update perception.evidence_items
    set
        title = 'Web Smoke Perception: Web Smoke Forward struggles',
        excerpt = 'Web Smoke Forward has a disappointing spell.'
    where source_id = source_one_id
      and external_id = 'web-smoke-perception-1';

    insert into perception.sources (
        code, display_name, source_kind, homepage_url, feed_url
    )
    values (
        'web-smoke-expert',
        'Web Smoke Expert',
        'expert',
        'https://example.net',
        'https://example.net/rating-feed.xml'
    )
    returning id into source_two_id;

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        source_one_id, 'web-smoke-rating-2',
        'https://example.com/web-smoke-rating-2',
        'Web Smoke Forward struggles in poor display',
        'Web Smoke Forward is criticised after a costly error.',
        now(), repeat('c', 64), '{"fixture":"rating"}'::jsonb, 'perception-v1.0'
    )
    returning id into evidence_id_value;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        evidence_id_value, player_id_value, 'Web Smoke Forward',
        'display_name_exact', 'Web Smoke Forward struggles in poor display'
    );

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        source_one_id, 'web-smoke-rating-3',
        'https://example.com/web-smoke-rating-3',
        'Web Smoke Forward criticised after costly error',
        'A poor night for Web Smoke Forward.',
        now(), repeat('d', 64), '{"fixture":"rating"}'::jsonb, 'perception-v1.0'
    )
    returning id into evidence_id_value;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        evidence_id_value, player_id_value, 'Web Smoke Forward',
        'display_name_exact', 'Web Smoke Forward criticised after costly error'
    );

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        source_two_id, 'web-smoke-rating-4',
        'https://example.net/web-smoke-rating-4',
        'Web Smoke Forward under fire after blunder',
        'Web Smoke Forward struggled again.',
        now(), repeat('e', 64), '{"fixture":"rating"}'::jsonb, 'perception-v1.0'
    )
    returning id into evidence_id_value;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        evidence_id_value, player_id_value, 'Web Smoke Forward',
        'display_name_exact', 'Web Smoke Forward under fire after blunder'
    );

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        source_two_id, 'web-smoke-rating-5',
        'https://example.net/web-smoke-rating-5',
        'Disappointing run continues for Web Smoke Forward',
        'Web Smoke Forward struggles to impress.',
        now(), repeat('f', 64), '{"fixture":"rating"}'::jsonb, 'perception-v1.0'
    )
    returning id into evidence_id_value;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        evidence_id_value, player_id_value, 'Web Smoke Forward',
        'display_name_exact', 'Disappointing run continues for Web Smoke Forward'
    );
end;
$$;
