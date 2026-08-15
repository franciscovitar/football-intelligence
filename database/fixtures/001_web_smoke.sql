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
    perception_source_id bigint;
    perception_evidence_id bigint;
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

    insert into perception.sources (
        code, display_name, source_kind, homepage_url, feed_url
    )
    values (
        'web-smoke-media',
        'Web Smoke Media',
        'media',
        'https://example.com',
        'https://example.com/feed.xml'
    )
    returning id into perception_source_id;

    insert into perception.evidence_items (
        source_id, external_id, canonical_url, title, excerpt,
        published_at, content_sha256, raw_metadata, ingestion_version
    )
    values (
        perception_source_id, 'web-smoke-perception-1',
        'https://example.com/web-smoke-perception',
        'Web Smoke Perception: Web Smoke Forward earns praise',
        'Web Smoke Forward is highlighted in deterministic external evidence.',
        now(), repeat('b', 64), '{"fixture":true}'::jsonb, 'perception-v1.0'
    )
    returning id into perception_evidence_id;

    insert into perception.player_evidence_mentions (
        evidence_id, player_id, matched_text, match_method, context_excerpt
    )
    values (
        perception_evidence_id, forward_id, 'Web Smoke Forward',
        'display_name_exact', 'Web Smoke Forward earns praise'
    );

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
        ),
        (
            forward_id, 'core:web-smoke-history', 'season', 'forward', 1.0,
            1800, 20, 68.0, 0.88,
            '{"scoring": 72.0, "creation": 65.0}'::jsonb,
            20, 'player-v1.0', now() - interval '1 year'
        );

    update analytics.player_score_snapshots
    set data_context = 'test_smoke'
    where scope_key like 'core:web-smoke%';

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

    insert into analytics.player_meta_snapshots (
        player_id, scope_key, role,
        performance_score, performance_confidence,
        form_score, form_confidence,
        stable_score, stable_confidence,
        expectation_score, expectation_confidence,
        surprise_delta, surprise_signal,
        trend_delta, trend_confidence, trend_signal,
        watchlist_score, watchlist_signal,
        history_seasons, baseline_evidence, trend_evidence,
        source_model_version, model_version, calculated_at
    )
    values
        (
            forward_id, 'core:web-smoke', 'forward',
            88, 0.90, 94, 0.82, 81.0, 0.86,
            68, 0.79, 20, 'surprise',
            7.5, 0.74, 'stable',
            84, 'breakout', 1,
            '[{"scope_key":"core:web-smoke-history","score":68,"confidence":0.88}]'::jsonb,
            '{"short_delta":7,"form_delta":6}'::jsonb,
            'player-v1.0', 'meta-v1.0', now()
        ),
        (
            midfielder_id, 'core:web-smoke', 'midfielder',
            84, 0.91, 82, 0.80, 84, 0.64,
            null, null, null, 'insufficient_history',
            -2, 0.80, 'stable',
            37.8, 'none', 0,
            '[]'::jsonb, '{"form_delta":-2}'::jsonb,
            'player-v1.0', 'meta-v1.0', now()
        ),
        (
            defender_id, 'core:web-smoke', 'defender',
            81, 0.89, 85, 0.81, 81, 0.62,
            null, null, null, 'insufficient_history',
            4, 0.81, 'stable',
            40.45, 'none', 0,
            '[]'::jsonb, '{"form_delta":4}'::jsonb,
            'player-v1.0', 'meta-v1.0', now()
        );

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
