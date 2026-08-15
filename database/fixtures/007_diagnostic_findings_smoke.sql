\set ON_ERROR_STOP on

-- Deterministic diagnostic findings for smoke-testing a future Diagnostics
-- read path without depending on a live analytics run. `entity_id` has no
-- foreign key (see the migration's comment), so this fixture is
-- self-contained and does not need to run after any other seed.
--
-- `data_context = 'test_smoke'` is set explicitly (not left to the column
-- default) so this fixture stays correct even if the default ever changes:
-- these rows must never become product-safe, regardless of whether a real
-- player/team later reuses the same entity_id.

do $$
begin
    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at,
        data_context, source_model_version, scope_key
    )
    values
        (
            'finishing_underperformance', 'player', 1, 'notable', 0.70000,
            '{"goals": 3, "goals_percentile": 25.0, "xg": 8.2, "xg_percentile": 78.0}'::jsonb,
            'role:forward', 'season', 'diagnostic-v1.0', now(),
            'test_smoke', 'player-v2.0', 'web-smoke'
        ),
        (
            'breakout_signal', 'player', 1, 'high', 0.72000,
            '{"watchlist_score": 86.0, "stable_score": 68.0}'::jsonb,
            'role:forward', 'stable', 'diagnostic-v1.0', now(),
            'test_smoke', 'player-v2.0', 'web-smoke'
        ),
        (
            'results_above_process', 'team', 1, 'notable', 0.75000,
            '{"results_process_delta": 15.0, "overall_score": 62.0}'::jsonb,
            'competition:ENG_PL:web-smoke', 'season', 'diagnostic-v1.0', now(),
            'test_smoke', 'team-v2.0', 'web-smoke'
        )
    on conflict (
        entity_type, entity_id, diagnostic_code, comparison_group, window_key,
        model_version, data_context, source_model_version, scope_key
    )
    do update set
        severity = excluded.severity,
        confidence = excluded.confidence,
        supporting_metrics = excluded.supporting_metrics,
        computed_at = excluded.computed_at;
end;
$$;
