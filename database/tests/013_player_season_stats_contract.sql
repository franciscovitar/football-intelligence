\set ON_ERROR_STOP on

begin;

do $$
declare
    player_id_value bigint;
    competition_id_value bigint;
    season_id_value bigint;
    row_count_after bigint;
begin
    if to_regclass('football.player_season_stats') is null then
        raise exception 'player_season_stats table is missing';
    end if;

    insert into football.players (display_name)
    values ('Season Stats Contract Player')
    returning id into player_id_value;

    insert into football.competitions (code, name)
    values ('CONTRACT_PSS', 'Contract Player Season Stats Competition')
    returning id into competition_id_value;

    insert into football.seasons (competition_id, label)
    values (competition_id_value, '2025/26')
    returning id into season_id_value;

    insert into football.player_season_stats (
        player_id, season_id, minutes, starts, goals, assists,
        expected_goals, expected_assists, influence, creativity, threat, ict_index,
        source, source_url, retrieved_at, semantic_version
    )
    values (
        player_id_value, season_id_value, 3120, 34, 18, 6,
        14.20, 4.10, 812.4, 210.5, 990.0, 209.9,
        'permitted-test-source', 'https://example.test/player-season/1',
        now(), 'permitted-test-source-v1'
    );

    -- Idempotent upsert on the (player, season, source) natural key.
    insert into football.player_season_stats (
        player_id, season_id, minutes, starts, goals, assists,
        source, source_url, retrieved_at, semantic_version
    )
    values (
        player_id_value, season_id_value, 3120, 34, 19, 6,
        'permitted-test-source', 'https://example.test/player-season/1',
        now(), 'permitted-test-source-v1'
    )
    on conflict (player_id, season_id, source)
    do update set goals = excluded.goals, updated_at = now();

    select count(*) into row_count_after
    from football.player_season_stats
    where player_id = player_id_value and season_id = season_id_value;

    if row_count_after <> 1 then
        raise exception 'expected idempotent upsert to keep exactly one row, got %', row_count_after;
    end if;

    if not exists (
        select 1 from football.player_season_stats
        where player_id = player_id_value and season_id = season_id_value and goals = 19
    ) then
        raise exception 'expected upsert to have updated goals to 19';
    end if;

    -- A second, disagreeing source for the same player-season is retained
    -- alongside the first, never averaged or overwritten.
    insert into football.player_season_stats (
        player_id, season_id, minutes, goals,
        source, source_url, retrieved_at, semantic_version
    )
    values (
        player_id_value, season_id_value, 3100, 17,
        'a-second-source', 'https://example.invalid/second-source',
        now(), 'a-second-source-v1'
    );

    select count(*) into row_count_after
    from football.player_season_stats
    where player_id = player_id_value and season_id = season_id_value;

    if row_count_after <> 2 then
        raise exception 'expected a second source to add a second row, got %', row_count_after;
    end if;

    begin
        insert into football.player_season_stats (
            player_id, season_id, goals,
            source, source_url, retrieved_at, semantic_version
        )
        values (
            player_id_value, season_id_value, -1,
            'contract-bad-goals', 'https://example.invalid', now(), 'v1'
        );
        raise exception 'expected negative goals to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into football.player_season_stats (
            player_id, season_id,
            source, source_url, retrieved_at, semantic_version
        )
        values (
            player_id_value, season_id_value,
            '', 'https://example.invalid', now(), 'v1'
        );
        raise exception 'expected blank source to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into football.player_season_stats (
            player_id, season_id, expected_goals,
            source, source_url, retrieved_at, semantic_version
        )
        values (
            player_id_value, season_id_value, -0.5,
            'contract-bad-xg', 'https://example.invalid', now(), 'v1'
        );
        raise exception 'expected negative expected_goals to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
