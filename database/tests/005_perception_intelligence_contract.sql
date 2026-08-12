\set ON_ERROR_STOP on

begin;

do $$
declare
    source_id_value bigint;
    evidence_id_value bigint;
    player_id_value bigint;
begin
    if to_regclass('perception.sources') is null then
        raise exception 'perception sources table is missing';
    end if;
    if to_regclass('perception.evidence_items') is null then
        raise exception 'perception evidence table is missing';
    end if;
    if to_regclass('perception.player_evidence_mentions') is null then
        raise exception 'perception mentions table is missing';
    end if;

    insert into perception.sources (
        code, display_name, source_kind, homepage_url, feed_url
    )
    values (
        'contract-media',
        'Contract Media',
        'media',
        'https://example.com',
        'https://example.com/feed.xml'
    )
    returning id into source_id_value;

    insert into football.players (display_name)
    values ('Perception Contract Player')
    returning id into player_id_value;

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        source_id_value,
        'contract-1',
        'https://example.com/article',
        'Perception Contract Player impresses',
        'Representative feed excerpt.',
        now(),
        repeat('a', 64),
        '{"fixture":true}'::jsonb,
        'perception-v1.0'
    )
    returning id into evidence_id_value;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        evidence_id_value,
        player_id_value,
        'Perception Contract Player',
        'display_name_exact',
        'Perception Contract Player impresses'
    );

    begin
        insert into perception.sources (
            code, display_name, source_kind, feed_url
        )
        values (
            'bad-source',
            'Bad Source',
            'influencer',
            'http://127.0.0.1/feed'
        );
        raise exception 'expected invalid source to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into perception.evidence_items (
            source_id, canonical_url, title, content_sha256, ingestion_version
        )
        values (
            source_id_value,
            'https://example.com/bad',
            'Bad hash',
            'not-a-hash',
            'perception-v1.0'
        );
        raise exception 'expected invalid evidence hash to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
