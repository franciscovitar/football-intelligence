\set ON_ERROR_STOP on

begin;

do $$
declare
    player_id_value bigint;
begin
    if to_regnamespace('analytics') is null then
        raise exception 'analytics schema is missing';
    end if;

    if to_regclass('analytics.player_feature_snapshots') is null
       or to_regclass('analytics.player_score_snapshots') is null then
        raise exception 'player analytics tables are missing';
    end if;

    insert into football.players (display_name)
    values ('Analytics Contract Player')
    returning id into player_id_value;

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
    values (
        player_id_value,
        'contract:2024',
        'season',
        'forward',
        'goals',
        900,
        10,
        0.5,
        0.45,
        75.0,
        20,
        'player-v1.0',
        now()
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
    values (
        player_id_value,
        'contract:2024',
        'season',
        'forward',
        0.95,
        900,
        10,
        72.5,
        0.80,
        '{"scoring": 80.0}'::jsonb,
        20,
        'player-v1.0',
        now()
    );

    begin
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
        values (
            player_id_value,
            'contract:invalid',
            'season',
            'forward',
            1.1,
            90,
            1,
            50,
            0.5,
            '{}'::jsonb,
            1,
            'player-v1.0',
            now()
        );

        raise exception 'expected invalid role confidence to be rejected';
    exception
        when check_violation then
            null;
    end;

    begin
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
        values (
            player_id_value,
            'contract:invalid',
            'season',
            'forward',
            'goals',
            90,
            1,
            0,
            0,
            101,
            1,
            'player-v1.0',
            now()
        );

        raise exception 'expected invalid percentile to be rejected';
    exception
        when check_violation then
            null;
    end;
end;
$$;

rollback;
