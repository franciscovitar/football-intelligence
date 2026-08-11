\set ON_ERROR_STOP on

begin;

do $$
declare
    provider_id_value bigint;
    competition_id_value bigint;
    season_id_value bigint;
    home_team_id_value bigint;
    away_team_id_value bigint;
    unrelated_team_id_value bigint;
    player_id_value bigint;
    match_id_value bigint;
    completed_run_id_value bigint;
begin
    if to_regnamespace('football') is null then
        raise exception 'football schema is missing';
    end if;

    if to_regnamespace('ingestion') is null then
        raise exception 'ingestion schema is missing';
    end if;

    if to_regclass('football.competitions') is null
       or to_regclass('football.seasons') is null
       or to_regclass('football.teams') is null
       or to_regclass('football.players') is null
       or to_regclass('football.matches') is null
       or to_regclass('football.competition_provider_ids') is null
       or to_regclass('football.team_provider_ids') is null
       or to_regclass('football.player_provider_ids') is null
       or to_regclass('football.match_provider_ids') is null
       or to_regclass('football.team_match_stats') is null
       or to_regclass('football.player_appearances') is null
       or to_regclass('football.player_match_stats') is null
       or to_regclass('ingestion.ingestion_runs') is null
       or to_regclass('ingestion.raw_objects') is null
       or to_regclass('ingestion.data_capabilities') is null then
        raise exception 'one or more required tables are missing';
    end if;

    select id
    into provider_id_value
    from ingestion.providers
    where code = 'api-football';

    if provider_id_value is null then
        raise exception 'API-Football seed is missing';
    end if;

    if (
        select count(*)
        from football.competitions
        where code in (
            'ARG_LPF',
            'ENG_PL',
            'ESP_LL',
            'ITA_SA',
            'GER_BL1',
            'FRA_L1'
        )
    ) <> 6 then
        raise exception 'core competition seeds are incomplete';
    end if;

    select id
    into competition_id_value
    from football.competitions
    where code = 'ENG_PL';

    insert into football.seasons (
        competition_id,
        label,
        starts_on,
        ends_on,
        is_current
    )
    values (
        competition_id_value,
        '2099/2100',
        date '2099-08-01',
        date '2100-05-31',
        true
    )
    returning id into season_id_value;

    begin
        insert into football.seasons (
            competition_id,
            label,
            is_current
        )
        values (
            competition_id_value,
            '2100/2101',
            true
        );

        raise exception 'expected one-current-season constraint to reject duplicate';
    exception
        when unique_violation then
            null;
    end;

    insert into football.teams (name, country_code)
    values ('Schema Test Home', 'ENG')
    returning id into home_team_id_value;

    insert into football.teams (name, country_code)
    values ('Schema Test Away', 'ENG')
    returning id into away_team_id_value;

    insert into football.teams (name, country_code)
    values ('Schema Test Unrelated', 'ENG')
    returning id into unrelated_team_id_value;

    insert into football.players (
        display_name,
        first_name,
        last_name,
        nationality_code
    )
    values (
        'Schema Test Player',
        'Schema',
        'Player',
        'ENG'
    )
    returning id into player_id_value;

    insert into football.matches (
        season_id,
        home_team_id,
        away_team_id,
        kickoff_at,
        status,
        home_score,
        away_score
    )
    values (
        season_id_value,
        home_team_id_value,
        away_team_id_value,
        timestamptz '2100-01-01 20:00:00+00',
        'finished',
        2,
        1
    )
    returning id into match_id_value;

    insert into football.team_match_stats (
        match_id,
        team_id,
        possession_pct,
        shots_total,
        shots_on_target
    )
    values (
        match_id_value,
        home_team_id_value,
        55.25,
        10,
        4
    );

    begin
        insert into football.team_match_stats (
            match_id,
            team_id,
            shots_total
        )
        values (
            match_id_value,
            unrelated_team_id_value,
            1
        );

        raise exception 'expected match/team membership trigger to reject team';
    exception
        when check_violation then
            null;
    end;

    insert into football.player_appearances (
        match_id,
        player_id,
        team_id,
        minutes,
        started
    )
    values (
        match_id_value,
        player_id_value,
        home_team_id_value,
        90,
        true
    );

    insert into football.player_match_stats (
        match_id,
        player_id,
        goals
    )
    values (
        match_id_value,
        player_id_value,
        0
    );

    if (
        select assists is not null
        from football.player_match_stats
        where match_id = match_id_value
          and player_id = player_id_value
    ) then
        raise exception 'missing player stat was collapsed to a non-null value';
    end if;

    begin
        update football.player_appearances
        set team_id = unrelated_team_id_value
        where match_id = match_id_value
          and player_id = player_id_value;

        raise exception 'expected appearance team trigger to reject team';
    exception
        when check_violation then
            null;
    end;

    insert into football.team_provider_ids (
        provider_id,
        team_id,
        external_id
    )
    values (
        provider_id_value,
        home_team_id_value,
        'schema-test-team-1'
    );

    begin
        insert into football.team_provider_ids (
            provider_id,
            team_id,
            external_id
        )
        values (
            provider_id_value,
            away_team_id_value,
            'schema-test-team-1'
        );

        raise exception 'expected provider external ID uniqueness violation';
    exception
        when unique_violation then
            null;
    end;

    begin
        insert into ingestion.ingestion_runs (
            provider_id,
            job_name,
            status
        )
        values (
            provider_id_value,
            'schema-contract-invalid',
            'succeeded'
        );

        raise exception 'expected completed ingestion run to require finished_at';
    exception
        when check_violation then
            null;
    end;

    insert into ingestion.ingestion_runs (
        provider_id,
        job_name,
        trigger_kind,
        status,
        finished_at,
        request_count,
        rows_written
    )
    values (
        provider_id_value,
        'schema-contract',
        'test',
        'succeeded',
        now(),
        1,
        1
    )
    returning id into completed_run_id_value;

    insert into ingestion.raw_objects (
        ingestion_run_id,
        storage_bucket,
        storage_path,
        endpoint,
        http_status,
        payload_sha256,
        byte_size
    )
    values (
        completed_run_id_value,
        'raw-provider',
        'schema-contract/object.json.gz',
        '/fixtures',
        200,
        repeat('a', 64),
        128
    );

    begin
        insert into ingestion.raw_objects (
            ingestion_run_id,
            storage_bucket,
            storage_path,
            endpoint
        )
        values (
            completed_run_id_value,
            'raw-provider',
            'schema-contract/object.json.gz',
            '/fixtures'
        );

        raise exception 'expected raw storage path uniqueness violation';
    exception
        when unique_violation then
            null;
    end;

    insert into ingestion.data_capabilities (
        provider_id,
        entity_type,
        metric_name,
        availability,
        sample_size,
        non_null_count
    )
    values (
        provider_id_value,
        'player_match_stats',
        'shots_total',
        'partial',
        10,
        7
    );

    begin
        insert into ingestion.data_capabilities (
            provider_id,
            entity_type,
            metric_name,
            availability,
            sample_size,
            non_null_count
        )
        values (
            provider_id_value,
            'player_match_stats',
            'invalid-count',
            'partial',
            10,
            11
        );

        raise exception 'expected capability count constraint to reject invalid counts';
    exception
        when check_violation then
            null;
    end;
end;
$$;

rollback;
