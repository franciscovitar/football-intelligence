\set ON_ERROR_STOP on

begin;

do $$
declare
    player_id_value bigint;
begin
    if to_regclass('analytics.player_meta_snapshots') is null then
        raise exception 'player meta snapshots table is missing';
    end if;

    insert into football.players (display_name)
    values ('Meta Contract Player')
    returning id into player_id_value;

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
    values (
        player_id_value, 'core:contract', 'forward',
        82, 0.8,
        88, 0.7,
        79, 0.75,
        68, 0.65,
        14, 'surprise',
        9, 0.6, 'rising',
        81, 'breakout',
        2,
        '[{"scope_key":"core:2023","score":68,"confidence":0.65}]'::jsonb,
        '{"short_delta":9}'::jsonb,
        'player-v1.0', 'meta-v1.0', now()
    );

    begin
        insert into analytics.player_meta_snapshots (
            player_id, scope_key, role,
            performance_score, performance_confidence,
            stable_score, stable_confidence,
            surprise_signal, trend_signal,
            watchlist_score, watchlist_signal,
            history_seasons, baseline_evidence, trend_evidence,
            source_model_version, model_version, calculated_at
        )
        values (
            player_id_value, 'core:invalid', 'striker',
            120, 1.2,
            50, 0.5,
            'lucky', 'hot',
            50, 'wonderkid',
            4, '{}'::jsonb, '[]'::jsonb,
            'player-v1.0', 'meta-v1.0', now()
        );
        raise exception 'expected invalid meta snapshot to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
