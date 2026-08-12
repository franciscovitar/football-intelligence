\set ON_ERROR_STOP on

do $$
declare
    forward_id bigint;
    midfielder_id bigint;
    defender_id bigint;
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
end;
$$;
