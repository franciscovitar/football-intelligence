\set ON_ERROR_STOP on

-- The Zero-Cost Coverage Lab never calls live providers in CI. This fixture
-- seeds deterministic coverage snapshots directly so /sources' coverage
-- matrix can be smoke-tested without spending any provider quota.

do $$
declare
    thesportsdb_id bigint;
    statsbomb_id bigint;
    football_data_org_id bigint;
    football_data_uk_id bigint;
begin
    select id into thesportsdb_id from ingestion.providers where code = 'thesportsdb';
    select id into statsbomb_id from ingestion.providers where code = 'statsbomb-open';
    select id into football_data_org_id from ingestion.providers where code = 'football-data-org';
    select id into football_data_uk_id from ingestion.providers where code = 'football-data-uk';

    insert into ingestion.coverage_snapshots (
        provider_id, competition_code, metric_name, granularity, entity_type,
        freshness_role, state, sample_size, observed_count,
        source_reference, last_checked_at
    )
    values
        (
            thesportsdb_id, 'GER_BL1', 'home_score', 'match', 'match',
            'current', 'current_available', 15, 15,
            'eventsseason.php?id=4331', now()
        ),
        (
            thesportsdb_id, 'GER_BL1', 'shots_total', 'team', 'team',
            'current', 'current_available', 2, 2,
            'lookupeventstats.php?id=2475153', now()
        ),
        (
            thesportsdb_id, 'GER_BL1', 'listed_position', 'player_appearance', 'player',
            'current', 'partial', 5, 5,
            'lookuplineup.php?id=2475153', now()
        ),
        (
            thesportsdb_id, 'ENG_PL', 'home_score', 'match', 'match',
            'current', 'not_probed', 0, 0,
            null, now()
        ),
        (
            statsbomb_id, 'GER_BL1', 'shots_total', 'player_match', 'player',
            'historical', 'historical_only', 2, 2,
            'statsbomb-open/data', now()
        ),
        (
            statsbomb_id, 'GER_BL1', 'home_score', 'match', 'match',
            'historical', 'partial', 306, 34,
            'statsbomb-open/data', now()
        ),
        (
            football_data_org_id, 'ENG_PL', 'home_score', 'match', 'match',
            'current', 'token_required', 0, 0,
            null, now()
        ),
        (
            football_data_uk_id, 'GER_BL1', 'shots_total', 'team', 'team',
            'current', 'current_available', 30, 30,
            'mmz4281/2526/D1.csv', now()
        ),
        (
            football_data_uk_id, 'ARG_LPF', 'home_score', 'match', 'match',
            'current', 'unsupported', 0, 0,
            null, now()
        )
    on conflict (provider_id, competition_code, metric_name, granularity, freshness_role)
    do update set
        state = excluded.state,
        sample_size = excluded.sample_size,
        observed_count = excluded.observed_count,
        last_checked_at = excluded.last_checked_at;
end;
$$;
