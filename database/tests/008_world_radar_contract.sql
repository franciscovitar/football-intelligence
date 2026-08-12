\set ON_ERROR_STOP on

begin;

do $$
begin
    if to_regclass('analytics.world_radar_snapshots') is null then
        raise exception 'world_radar_snapshots table is missing';
    end if;

    insert into analytics.world_radar_snapshots (
        provider_code, provider_player_id, player_name, team_name,
        competition_code, competition_name, country, season_label,
        position, appearances, minutes, goals, assists,
        metrics, radar_score, confidence, reasons, source_lists,
        model_version, calculated_at
    )
    values (
        'api-football', 'contract-player-1', 'Contract Candidate', 'Contract FC',
        'NED_ED', 'Eredivisie', 'Netherlands', '2024',
        'Attacker', 20, 1500, 15, 5,
        '{"goals_per90":0.9}'::jsonb, 88.5, 0.72,
        '["top_scorer_feed","elite_goals_per90"]'::jsonb,
        '["topscorers"]'::jsonb,
        'world-radar-v1.0', now()
    );

    -- Idempotent upsert on the natural key.
    insert into analytics.world_radar_snapshots (
        provider_code, provider_player_id, player_name, team_name,
        competition_code, competition_name, country, season_label,
        position, appearances, minutes, goals, assists,
        metrics, radar_score, confidence, reasons, source_lists,
        model_version, calculated_at
    )
    values (
        'api-football', 'contract-player-2', 'Contract Candidate Two', 'Contract FC',
        'NED_ED', 'Eredivisie', 'Netherlands', '2024',
        'Midfielder', 18, 1400, 4, 10,
        '{"assists_per90":0.6}'::jsonb, 76.0, 0.65,
        '["top_assist_feed"]'::jsonb,
        '["topassists"]'::jsonb,
        'world-radar-v1.0', now()
    );

    begin
        insert into analytics.world_radar_snapshots (
            provider_code, provider_player_id, player_name, team_name,
            competition_code, competition_name, country, season_label,
            position, appearances, minutes, goals, assists,
            metrics, radar_score, confidence, reasons, source_lists,
            model_version, calculated_at
        )
        values (
            'api-football', 'contract-player-3', 'Out Of Range Score', null,
            'NED_ED', 'Eredivisie', 'Netherlands', '2024',
            'Attacker', 10, 900, 3, 1,
            '{}'::jsonb, 150.0, 0.5,
            '[]'::jsonb, '[]'::jsonb,
            'world-radar-v1.0', now()
        );
        raise exception 'expected out-of-range radar_score to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.world_radar_snapshots (
            provider_code, provider_player_id, player_name, team_name,
            competition_code, competition_name, country, season_label,
            position, appearances, minutes, goals, assists,
            metrics, radar_score, confidence, reasons, source_lists,
            model_version, calculated_at
        )
        values (
            'api-football', 'contract-player-4', 'Out Of Range Confidence', null,
            'NED_ED', 'Eredivisie', 'Netherlands', '2024',
            'Attacker', 10, 900, 3, 1,
            '{}'::jsonb, 50.0, 1.5,
            '[]'::jsonb, '[]'::jsonb,
            'world-radar-v1.0', now()
        );
        raise exception 'expected out-of-range confidence to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.world_radar_snapshots (
            provider_code, provider_player_id, player_name, team_name,
            competition_code, competition_name, country, season_label,
            position, appearances, minutes, goals, assists,
            metrics, radar_score, confidence, reasons, source_lists,
            model_version, calculated_at
        )
        values (
            'api-football', 'contract-player-5', '', null,
            'NED_ED', 'Eredivisie', 'Netherlands', '2024',
            'Attacker', 10, 900, 3, 1,
            '{}'::jsonb, 50.0, 0.5,
            '[]'::jsonb, '[]'::jsonb,
            'world-radar-v1.0', now()
        );
        raise exception 'expected blank player_name to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
