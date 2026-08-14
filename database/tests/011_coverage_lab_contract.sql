\set ON_ERROR_STOP on

begin;

do $$
declare
    statsbomb_id bigint;
    row_count_before bigint;
    row_count_after bigint;
begin
    if to_regclass('ingestion.coverage_snapshots') is null then
        raise exception 'coverage_snapshots table is missing';
    end if;

    select id into statsbomb_id from ingestion.providers where code = 'statsbomb-open';
    if statsbomb_id is null then
        raise exception 'statsbomb-open provider seed is missing';
    end if;
    if not exists (select 1 from ingestion.providers where code = 'football-data-org') then
        raise exception 'football-data-org provider seed is missing';
    end if;

    insert into ingestion.coverage_snapshots (
        provider_id, competition_code, metric_name, granularity, entity_type,
        freshness_role, state, sample_size, observed_count,
        source_reference, last_checked_at
    )
    values (
        statsbomb_id, 'GER_BL1', 'shots_total', 'player_match', 'player',
        'historical', 'historical_only', 34, 34,
        'data/events/contract.json', now()
    );

    select count(*) into row_count_before
    from ingestion.coverage_snapshots
    where provider_id = statsbomb_id and competition_code = 'GER_BL1' and metric_name = 'shots_total';

    -- Idempotent upsert on the natural key.
    insert into ingestion.coverage_snapshots (
        provider_id, competition_code, metric_name, granularity, entity_type,
        freshness_role, state, sample_size, observed_count,
        source_reference, last_checked_at
    )
    values (
        statsbomb_id, 'GER_BL1', 'shots_total', 'player_match', 'player',
        'historical', 'historical_only', 34, 30,
        'data/events/contract.json', now()
    )
    on conflict (provider_id, competition_code, metric_name, granularity, freshness_role)
    do update set
        state = excluded.state,
        sample_size = excluded.sample_size,
        observed_count = excluded.observed_count,
        last_checked_at = excluded.last_checked_at;

    select count(*) into row_count_after
    from ingestion.coverage_snapshots
    where provider_id = statsbomb_id and competition_code = 'GER_BL1' and metric_name = 'shots_total';

    if row_count_before <> 1 or row_count_after <> 1 then
        raise exception 'expected idempotent upsert to keep exactly one row, got % then %',
            row_count_before, row_count_after;
    end if;

    begin
        insert into ingestion.coverage_snapshots (
            provider_id, competition_code, metric_name, granularity, entity_type,
            freshness_role, state, sample_size, observed_count, last_checked_at
        )
        values (
            statsbomb_id, 'GER_BL1', 'contract-bad-state', 'player_match', 'player',
            'historical', 'guessed', 1, 1, now()
        );
        raise exception 'expected invalid coverage state to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into ingestion.coverage_snapshots (
            provider_id, competition_code, metric_name, granularity, entity_type,
            freshness_role, state, sample_size, observed_count, last_checked_at
        )
        values (
            statsbomb_id, 'GER_BL1', 'contract-bad-count', 'player_match', 'player',
            'current', 'partial', 5, 10, now()
        );
        raise exception 'expected observed_count exceeding sample_size to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into ingestion.coverage_snapshots (
            provider_id, competition_code, metric_name, granularity, entity_type,
            freshness_role, state, sample_size, observed_count, last_checked_at
        )
        values (
            statsbomb_id, 'GER_BL1', 'contract-bad-granularity', 'season', 'player',
            'historical', 'historical_only', 1, 1, now()
        );
        raise exception 'expected invalid granularity to be rejected';
    exception
        when check_violation then null;
    end;

    -- `previous_season` (Block 15 corrective pass): a `current`-role
    -- provider's probe that verified only the latest completed season, not
    -- the true current one -- must be an accepted state, distinct from
    -- `current_available`.
    insert into ingestion.coverage_snapshots (
        provider_id, competition_code, metric_name, granularity, entity_type,
        freshness_role, state, sample_size, observed_count, last_checked_at
    )
    values (
        statsbomb_id, 'GER_BL1', 'contract-previous-season', 'match', 'match',
        'current', 'previous_season', 15, 15, now()
    );
end;
$$;

rollback;
