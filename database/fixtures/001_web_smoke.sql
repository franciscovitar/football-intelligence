\set ON_ERROR_STOP on

do $$
declare
    forward_id bigint;
    midfielder_id bigint;
    defender_id bigint;
    competition_id_value bigint;
    season_id_value bigint;
    team_home_id bigint;
    team_away_id bigint;
    team_match_id bigint;
begin
    insert into football.players (display_name, nationality_code)
    values ('Web Smoke Forward', 'ARG')
    returning id into forward_id;

    insert into football.players (display_name, nationality_code)
    values ('Web Smoke Midfielder', 'ESP')
    returning id into midfielder_id;

    insert into football.players (display_name, nationality_code)
    values ('Web Smoke Defender', 'ITA')
    returning id into defender_id;

    insert into analytics.player_score_snapshots (
        player_id,
        scope_key,
        window_key,
        role,
        role_confidence,
        minutes,
        appearances,
        overall_score,
        confidence,
        dimension_scores,
        reference_sample_size,
        model_version,
        calculated_at
    )
    values
        (
            forward_id, 'core:web-smoke', 'season', 'forward', 1.0,
            900, 10, 88.0, 0.90,
            '{"scoring": 92.0, "creation": 78.0, "carrying": 84.0}'::jsonb,
            20, 'player-v1.0', now()
        ),
        (
            forward_id, 'core:web-smoke', 'last_10', 'forward', 1.0,
            810, 9, 89.0, 0.88,
            '{"scoring": 93.0, "creation": 79.0, "carrying": 84.0}'::jsonb,
            20, 'player-v1.0', now()
        ),
        (
            forward_id, 'core:web-smoke', 'last_5', 'forward', 1.0,
            450, 5, 94.0, 0.82,
            '{"scoring": 97.0, "creation": 82.0, "carrying": 86.0}'::jsonb,
            20, 'player-v1.0', now()
        ),
        (
            forward_id, 'core:web-smoke', 'last_3', 'forward', 1.0,
            270, 3, 96.0, 0.72,
            '{"scoring": 98.0, "creation": 84.0, "carrying": 87.0}'::jsonb,
            20, 'player-v1.0', now()
        ),
        (
            midfielder_id, 'core:web-smoke', 'season', 'midfielder', 0.95,
            1080, 12, 84.0, 0.91,
            '{"scoring": 68.0, "creation": 91.0, "carrying": 87.0, "defending": 76.0}'::jsonb,
            24, 'player-v1.0', now()
        ),
        (
            midfielder_id, 'core:web-smoke', 'last_5', 'midfielder', 0.95,
            430, 5, 82.0, 0.80,
            '{"scoring": 65.0, "creation": 89.0, "carrying": 86.0, "defending": 74.0}'::jsonb,
            24, 'player-v1.0', now()
        ),
        (
            defender_id, 'core:web-smoke', 'season', 'defender', 1.0,
            990, 11, 81.0, 0.89,
            '{"defending": 92.0, "creation": 61.0, "carrying": 58.0}'::jsonb,
            22, 'player-v1.0', now()
        ),
        (
            defender_id, 'core:web-smoke', 'last_5', 'defender', 1.0,
            450, 5, 85.0, 0.81,
            '{"defending": 95.0, "creation": 62.0, "carrying": 60.0}'::jsonb,
            22, 'player-v1.0', now()
        );

    insert into analytics.player_feature_snapshots (
        player_id,
        scope_key,
        window_key,
        role,
        metric_name,
        minutes,
        appearances,
        raw_per90,
        adjusted_per90,
        percentile,
        reference_sample_size,
        model_version,
        calculated_at
    )
    values
        (forward_id, 'core:web-smoke', 'season', 'forward', 'goals', 900, 10, 0.80, 0.80, 96, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'season', 'forward', 'shots_on_target', 900, 10, 2.70, 2.70, 94, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'season', 'forward', 'key_passes', 900, 10, 1.80, 1.80, 81, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'season', 'forward', 'dribbles_successful', 900, 10, 2.10, 2.10, 84, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'last_5', 'forward', 'goals', 450, 5, 1.20, 1.20, 99, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'last_5', 'forward', 'shots_on_target', 450, 5, 3.20, 3.20, 97, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'last_5', 'forward', 'key_passes', 450, 5, 2.20, 2.20, 86, 20, 'player-v1.0', now()),
        (forward_id, 'core:web-smoke', 'last_5', 'forward', 'dribbles_successful', 450, 5, 2.40, 2.40, 88, 20, 'player-v1.0', now()),
        (midfielder_id, 'core:web-smoke', 'season', 'midfielder', 'key_passes', 1080, 12, 2.60, 2.60, 93, 24, 'player-v1.0', now()),
        (midfielder_id, 'core:web-smoke', 'season', 'midfielder', 'assists', 1080, 12, 0.45, 0.45, 88, 24, 'player-v1.0', now()),
        (defender_id, 'core:web-smoke', 'season', 'defender', 'tackles', 990, 11, 2.80, 3.10, 95, 22, 'player-v1.0', now()),
        (defender_id, 'core:web-smoke', 'season', 'defender', 'interceptions', 990, 11, 2.20, 2.45, 93, 22, 'player-v1.0', now());

    select id into competition_id_value
    from football.competitions
    where code = 'ENG_PL';

    insert into football.seasons (competition_id, label)
    values (competition_id_value, 'web-smoke')
    returning id into season_id_value;

    insert into football.teams (name, country_code)
    values ('Web Smoke United', 'ENG')
    returning id into team_home_id;

    insert into football.teams (name, country_code)
    values ('Web Smoke City', 'ENG')
    returning id into team_away_id;

    insert into football.matches (
        season_id, home_team_id, away_team_id, kickoff_at,
        status, home_score, away_score
    )
    values (
        season_id_value, team_home_id, team_away_id,
        now() - interval '1 day', 'finished', 2, 1
    )
    returning id into team_match_id;

    insert into football.team_match_stats (
        match_id, team_id, possession_pct, shots_total,
        shots_on_target, shots_inside_box, corners, passes_total, passes_accurate
    )
    values
        (team_match_id, team_home_id, 61, 16, 7, 11, 8, 620, 558),
        (team_match_id, team_away_id, 39, 7, 2, 3, 2, 360, 270);

    insert into analytics.team_score_snapshots (
        team_id, season_id, scope_key, window_key, matches,
        overall_score, confidence, dimension_scores,
        results_process_delta, results_process_signal, diagnostics,
        reference_sample_size, current_elo, elo_change_last_5,
        model_version, calculated_at
    )
    values
        (
            team_home_id, season_id_value, 'competition:ENG_PL:web-smoke',
            'season', 10, 86, 0.82,
            '{"attack": 88, "chance_generation": 91, "finishing_proxy": 74, "defense": 84, "control": 89, "process": 88, "results": 82}'::jsonb,
            -6, 'results_aligned', '{"signals": [], "metric_coverage": 1}'::jsonb,
            20, 1578, 22, 'team-v1.0', now()
        ),
        (
            team_home_id, season_id_value, 'competition:ENG_PL:web-smoke',
            'last_5', 5, 90, 0.70,
            '{"attack": 91, "chance_generation": 94, "finishing_proxy": 77, "defense": 86, "control": 90, "process": 91, "results": 88}'::jsonb,
            -3, 'results_aligned', '{"signals": [], "metric_coverage": 1}'::jsonb,
            20, 1578, 22, 'team-v1.0', now()
        ),
        (
            team_away_id, season_id_value, 'competition:ENG_PL:web-smoke',
            'season', 10, 58, 0.78,
            '{"attack": 48, "chance_generation": 42, "finishing_proxy": 65, "defense": 44, "control": 38, "process": 42, "results": 72}'::jsonb,
            30, 'results_above_process',
            '{"signals": ["results_above_process"], "metric_coverage": 1}'::jsonb,
            20, 1492, -10, 'team-v1.0', now()
        ),
        (
            team_away_id, season_id_value, 'competition:ENG_PL:web-smoke',
            'last_5', 5, 52, 0.66,
            '{"attack": 45, "chance_generation": 38, "finishing_proxy": 68, "defense": 40, "control": 35, "process": 38, "results": 64}'::jsonb,
            26, 'results_above_process',
            '{"signals": ["results_above_process"], "metric_coverage": 1}'::jsonb,
            20, 1492, -10, 'team-v1.0', now()
        );

    insert into analytics.team_feature_snapshots (
        team_id, season_id, scope_key, window_key, metric_name,
        matches, observed_matches, raw_value, adjusted_value,
        percentile, reference_sample_size, model_version, calculated_at
    )
    values
        (team_home_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'shots_total_for', 5, 5, 16, 16, 95, 20, 'team-v1.0', now()),
        (team_home_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'shots_on_target_for', 5, 5, 7, 7, 96, 20, 'team-v1.0', now()),
        (team_home_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'possession_pct', 5, 5, 61, 61, 90, 20, 'team-v1.0', now()),
        (team_home_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'goals_per_shot', 5, 5, 0.13, 0.12, 73, 20, 'team-v1.0', now()),
        (team_away_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'shots_total_for', 5, 5, 7, 7, 25, 20, 'team-v1.0', now()),
        (team_away_id, season_id_value, 'competition:ENG_PL:web-smoke', 'last_5', 'goals_per_shot', 5, 5, 0.20, 0.15, 82, 20, 'team-v1.0', now());

    insert into analytics.team_elo_history (
        match_id, team_id, opponent_team_id, season_id,
        pre_match_rating, opponent_pre_match_rating,
        expected_result, actual_result, post_match_rating,
        model_version, calculated_at
    )
    values
        (team_match_id, team_home_id, team_away_id, season_id_value, 1500, 1500, 0.585499, 1, 1508.2900, 'team-v1.0', now()),
        (team_match_id, team_away_id, team_home_id, season_id_value, 1500, 1500, 0.414501, 0, 1491.7100, 'team-v1.0', now());
end;
$$;
