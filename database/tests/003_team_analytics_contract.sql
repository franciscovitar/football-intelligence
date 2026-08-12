\set ON_ERROR_STOP on

begin;

do $$
declare
    competition_id_value bigint;
    season_id_value bigint;
    home_team_id_value bigint;
    away_team_id_value bigint;
    match_id_value bigint;
begin
    if to_regclass('analytics.team_feature_snapshots') is null
       or to_regclass('analytics.team_score_snapshots') is null
       or to_regclass('analytics.team_elo_history') is null then
        raise exception 'team analytics tables are missing';
    end if;

    insert into football.competitions (code, name)
    values ('TEAM_CONTRACT', 'Team Contract Competition')
    returning id into competition_id_value;

    insert into football.seasons (competition_id, label)
    values (competition_id_value, 'contract')
    returning id into season_id_value;

    insert into football.teams (name)
    values ('Team Contract Home')
    returning id into home_team_id_value;

    insert into football.teams (name)
    values ('Team Contract Away')
    returning id into away_team_id_value;

    insert into football.matches (
        season_id, home_team_id, away_team_id, kickoff_at,
        status, home_score, away_score
    )
    values (
        season_id_value, home_team_id_value, away_team_id_value,
        now(), 'finished', 2, 1
    )
    returning id into match_id_value;

    insert into analytics.team_feature_snapshots (
        team_id, season_id, scope_key, window_key, metric_name,
        matches, observed_matches, raw_value, adjusted_value,
        percentile, reference_sample_size, model_version, calculated_at
    )
    values (
        home_team_id_value, season_id_value, 'competition:TEAM_CONTRACT:contract',
        'season', 'shots_total_for', 1, 1, 12, 12, 75, 2, 'team-v1.0', now()
    );

    insert into analytics.team_score_snapshots (
        team_id, season_id, scope_key, window_key, matches,
        overall_score, confidence, dimension_scores,
        results_process_delta, results_process_signal, diagnostics,
        reference_sample_size, current_elo, elo_change_last_5,
        model_version, calculated_at
    )
    values (
        home_team_id_value, season_id_value, 'competition:TEAM_CONTRACT:contract',
        'season', 1, 70, 0.2, '{"process": 72, "results": 68}'::jsonb,
        -4, 'results_aligned', '{"signals": []}'::jsonb,
        2, 1508, 8, 'team-v1.0', now()
    );

    insert into analytics.team_elo_history (
        match_id, team_id, opponent_team_id, season_id,
        pre_match_rating, opponent_pre_match_rating,
        expected_result, actual_result, post_match_rating,
        model_version, calculated_at
    )
    values (
        match_id_value, home_team_id_value, away_team_id_value, season_id_value,
        1500, 1500, 0.585499, 1, 1508.29, 'team-v1.0', now()
    );

    begin
        insert into analytics.team_feature_snapshots (
            team_id, season_id, scope_key, window_key, metric_name,
            matches, observed_matches, raw_value, adjusted_value,
            percentile, reference_sample_size, model_version, calculated_at
        )
        values (
            away_team_id_value, season_id_value, 'contract:invalid',
            'season', 'possession_pct', 1, 2, 50, 50, 50, 2, 'team-v1.0', now()
        );
        raise exception 'expected observed matches above matches to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.team_score_snapshots (
            team_id, season_id, scope_key, window_key, matches,
            overall_score, confidence, dimension_scores,
            results_process_delta, results_process_signal, diagnostics,
            reference_sample_size, current_elo, elo_change_last_5,
            model_version, calculated_at
        )
        values (
            away_team_id_value, season_id_value, 'contract:invalid',
            'season', 1, 50, 1.1, '{}'::jsonb,
            0, 'lucky', '{}'::jsonb, 2, 1500, 0, 'team-v1.0', now()
        );
        raise exception 'expected invalid confidence/signal to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.team_elo_history (
            match_id, team_id, opponent_team_id, season_id,
            pre_match_rating, opponent_pre_match_rating,
            expected_result, actual_result, post_match_rating,
            model_version, calculated_at
        )
        values (
            match_id_value, away_team_id_value, home_team_id_value, season_id_value,
            1500, 1500, 0.414501, 0.25, 1491.71, 'team-v1.0', now()
        );
        raise exception 'expected invalid Elo result to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
