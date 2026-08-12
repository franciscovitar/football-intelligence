\set ON_ERROR_STOP on

begin;

do $$
declare
    player_id_value bigint;
begin
    if to_regclass('analytics.player_rating_snapshots') is null then
        raise exception 'player rating snapshots table is missing';
    end if;

    insert into football.players (display_name)
    values ('Rating Contract Player')
    returning id into player_id_value;

    insert into analytics.player_rating_snapshots (
        player_id, scope_key, role,
        performance_score, performance_confidence,
        perception_score, perception_confidence, perception_signal,
        rating_gap, rating_confidence, rating_signal,
        consensus_score, polarization_score,
        evidence_count, scored_evidence_count,
        source_count, scored_source_count, evidence_window_days,
        evidence_breakdown,
        performance_model_version, perception_model_version,
        model_version, calculated_at
    )
    values (
        player_id_value, 'core:contract', 'forward',
        80, 0.90,
        55, 0.70, 'positive',
        25, 0.70, 'underrated',
        72, 12,
        5, 5,
        2, 2, 180,
        '[{"evidence_id":1}]'::jsonb,
        'meta-v1.0', 'perception-v1.0',
        'rating-v1.0', now()
    );

    begin
        insert into analytics.player_rating_snapshots (
            player_id, scope_key, role,
            performance_score, performance_confidence,
            perception_confidence, perception_signal,
            rating_confidence, rating_signal,
            evidence_count, scored_evidence_count,
            source_count, scored_source_count, evidence_window_days,
            evidence_breakdown,
            performance_model_version, perception_model_version,
            model_version, calculated_at
        )
        values (
            player_id_value, 'core:bad', 'forward',
            80, 0.90,
            0.70, 'positive',
            0.70, 'certainly-underrated',
            1, 2,
            1, 1, 180,
            '[]'::jsonb,
            'meta-v1.0', 'perception-v1.0',
            'rating-v1.0', now()
        );
        raise exception 'expected invalid rating row to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
