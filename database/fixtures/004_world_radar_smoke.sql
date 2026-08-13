\set ON_ERROR_STOP on

-- World Radar V1 never calls the live provider in CI. This fixture seeds
-- deterministic snapshots directly so /radar can be smoke-tested without
-- spending real API-Football quota.

insert into analytics.world_radar_snapshots (
    provider_code, provider_player_id, player_name, team_name,
    competition_code, competition_name, country, season_label,
    position, appearances, minutes, goals, assists,
    metrics, radar_score, confidence, reasons, source_lists,
    model_version, calculated_at
)
values
    (
        'api-football', 'web-smoke-radar-1', 'Web Smoke Radar Forward', 'Web Smoke Radar FC',
        'NED_ED', 'Eredivisie', 'Netherlands', 'web-smoke',
        'Attacker', 22, 1800, 18, 6,
        '{"goals_per90":0.9,"assists_per90":0.3,"shots_on_target_per90":2.1,"key_passes_per90":1.1,"successful_dribbles_per90":1.4}'::jsonb,
        91.25, 0.81,
        '["top_scorer_feed","top_assist_feed","elite_goals_per90"]'::jsonb,
        '["topscorers","topassists"]'::jsonb,
        'world-radar-v1.0', now()
    ),
    (
        'api-football', 'web-smoke-radar-2', 'Web Smoke Radar Playmaker', 'Web Smoke Radar FC',
        'NED_ED', 'Eredivisie', 'Netherlands', 'web-smoke',
        'Midfielder', 20, 1650, 4, 12,
        '{"goals_per90":0.22,"assists_per90":0.65,"shots_on_target_per90":0.5,"key_passes_per90":2.4,"successful_dribbles_per90":1.1}'::jsonb,
        84.10, 0.76,
        '["top_assist_feed","elite_creation_per90"]'::jsonb,
        '["topassists"]'::jsonb,
        'world-radar-v1.0', now()
    )
on conflict (provider_code, provider_player_id, competition_code, season_label, model_version)
do update set
    radar_score = excluded.radar_score,
    confidence = excluded.confidence,
    calculated_at = excluded.calculated_at;
