\set ON_ERROR_STOP on

begin;

do $$
declare
    competition_id_value bigint;
    season_id_value bigint;
    real_player_id bigint;
    partial_player_id bigint;
    smoke_player_id bigint;
    real_team_id bigint;
    partial_team_id bigint;
    smoke_team_id bigint;
begin
    if to_regclass('analytics.product_player_detail_v2') is null
       or to_regclass('analytics.product_player_ranking_candidates_v2') is null
       or to_regclass('analytics.product_team_detail_v2') is null
       or to_regclass('analytics.product_team_ranking_candidates_v2') is null
       or to_regclass('analytics.product_player_watchlist_v2') is null then
        raise exception 'Block 17 product read models are missing';
    end if;

    insert into football.competitions (code, name)
    values ('PRODUCT_V2', 'Product V2 Contract') returning id into competition_id_value;
    insert into football.seasons (competition_id, label)
    values (competition_id_value, '2025/26') returning id into season_id_value;
    insert into football.players (display_name) values ('Product Real Eligible') returning id into real_player_id;
    insert into football.players (display_name) values ('Product Real Partial') returning id into partial_player_id;
    insert into football.players (display_name) values ('Product Smoke Hidden') returning id into smoke_player_id;
    insert into football.teams (name) values ('Product Real Team') returning id into real_team_id;
    insert into football.teams (name) values ('Product Partial Team') returning id into partial_team_id;
    insert into football.teams (name) values ('Product Smoke Team') returning id into smoke_team_id;

    insert into analytics.player_score_snapshots (
        player_id, scope_key, window_key, role, role_confidence, minutes,
        appearances, overall_score, confidence, dimension_scores,
        reference_sample_size, model_version, calculated_at, data_context,
        evidence_coverage_pct, evidence_state, dimension_evidence
    ) values
    (real_player_id, 'product:v2', 'season', 'forward', 1, 600, 8, 82, .8,
     '{"finishing": 88}', 20, 'player-v2.0', now(), 'real', 90, 'ready',
     '{"finishing":{"score":88,"evidence_coverage_pct":100,"evidence_state":"ready","evidence_metrics_available":["goals","xg"],"evidence_metrics_missing":[],"evidence_core_metrics":["goals","xg"]}}'),
    (partial_player_id, 'product:v2', 'season', 'midfielder', 1, 200, 4, null, .8,
     '{}', 20, 'player-v2.0', now(), 'real', 45, 'partial',
     '{"creation":{"score":null,"evidence_coverage_pct":45,"evidence_state":"partial","evidence_metrics_available":["key_passes"],"evidence_metrics_missing":["xa"],"evidence_core_metrics":["xa"]}}'),
    (smoke_player_id, 'product:v2', 'season', 'forward', 1, 900, 10, 99, .99,
     '{"finishing": 99}', 20, 'player-v2.0', now(), 'test_smoke', 100, 'ready', '{}');

    if not exists (select 1 from analytics.product_player_detail_v2 where player_id = partial_player_id) then
        raise exception 'real partial player must remain available to detail';
    end if;
    if exists (select 1 from analytics.product_player_detail_v2 where player_id = smoke_player_id) then
        raise exception 'test_smoke player leaked into product detail';
    end if;
    if not exists (select 1 from analytics.product_player_ranking_candidates_v2 where player_id = real_player_id) then
        raise exception 'eligible real player missing from ranking candidates';
    end if;
    if exists (select 1 from analytics.product_player_ranking_candidates_v2 where player_id = partial_player_id) then
        raise exception 'tiny-sample partial player leaked into ranking candidates';
    end if;

    insert into analytics.team_score_snapshots (
        team_id, season_id, scope_key, window_key, matches, overall_score,
        confidence, dimension_scores, diagnostics, reference_sample_size,
        model_version, calculated_at, evidence_coverage_pct, evidence_state,
        dimension_evidence, data_context
    ) values
    (real_team_id, season_id_value, 'product:v2', 'season', 12, 78, .75,
     '{"attack":80}', '{"signals":[]}', 20, 'team-v2.0', now(), 90, 'ready',
     '{"attack":{"score":80,"evidence_coverage_pct":100,"evidence_state":"ready","evidence_metrics_available":["xg"],"evidence_metrics_missing":[],"evidence_core_metrics":["xg"]}}', 'real'),
    (partial_team_id, season_id_value, 'product:v2', 'season', 12, null, .7,
     '{}', '{"signals":[]}', 20, 'team-v2.0', now(), 40, 'partial',
     '{"pressing":{"score":null,"evidence_coverage_pct":0,"evidence_state":"insufficient_data","evidence_metrics_available":[],"evidence_metrics_missing":["ppda"],"evidence_core_metrics":["ppda"]}}', 'real'),
    (smoke_team_id, season_id_value, 'product:v2', 'season', 12, 99, .99,
     '{}', '{"signals":[]}', 20, 'team-v2.0', now(), 100, 'ready', '{}', 'test_smoke');

    if not exists (select 1 from analytics.product_team_detail_v2 where team_id = partial_team_id) then
        raise exception 'real partial team must remain available to detail';
    end if;
    if exists (select 1 from analytics.product_team_detail_v2 where team_id = smoke_team_id) then
        raise exception 'test_smoke team leaked into product detail';
    end if;
    if not exists (select 1 from analytics.product_team_ranking_candidates_v2 where team_id = real_team_id) then
        raise exception 'eligible real team missing from ranking candidates';
    end if;

    insert into analytics.player_watchlist_entries (player_id, category, reason)
    values (real_player_id, 'manual', 'real contract'), (smoke_player_id, 'manual', 'must stay hidden');
    if not exists (select 1 from analytics.product_player_watchlist_v2 where player_id = real_player_id) then
        raise exception 'real V2 watchlist entry missing';
    end if;
    if exists (select 1 from analytics.product_player_watchlist_v2 where player_id = smoke_player_id) then
        raise exception 'test-only player leaked into product watchlist';
    end if;

    -- Diagnostic findings must never be treated as product-safe merely
    -- because their entity_id happens to be real V2: only a finding whose
    -- OWN data_context is 'real', whose source_model_version matches the
    -- corresponding V2 statistical model, and whose scope_key matches the
    -- currently active scope may appear in `product_player_diagnostic_findings_v2`
    -- / `product_team_diagnostic_findings_v2`. `real_player_id` and
    -- `real_team_id` are real V2 entities (inserted above with scope_key
    -- 'product:v2'), which makes them the exact leak vector this contract
    -- protects against.
    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at,
        data_context, source_model_version, scope_key
    ) values
        -- smoke diagnostic on a real player id: must stay hidden.
        ('contract-smoke-on-real-id', 'player', real_player_id, 'notable', 0.7,
         '{"x": 1}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(),
         'test_smoke', 'player-v2.0', 'product:v2'),
        -- real diagnostic sourced from V1 stats on a real V2 entity: must stay hidden.
        ('contract-v1-source-on-real-v2', 'player', real_player_id, 'notable', 0.7,
         '{"x": 1}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(),
         'real', 'player-v1.0', 'product:v2'),
        -- real, correctly-sourced, but tied to a scope that is not the active one: must stay hidden.
        ('contract-stale-scope', 'player', real_player_id, 'notable', 0.7,
         '{"x": 1}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(),
         'real', 'player-v2.0', 'product:v2-stale'),
        -- explicitly real player-v2.0 finding in the active scope: must appear.
        ('contract-real-player-v2', 'player', real_player_id, 'notable', 0.7,
         '{"x": 1}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(),
         'real', 'player-v2.0', 'product:v2'),
        -- explicitly real team-v2.0 finding in the active scope: must appear.
        ('contract-real-team-v2', 'team', real_team_id, 'notable', 0.7,
         '{"x": 1}'::jsonb, 'competition:ENG_PL:2025', 'season', 'diagnostic-v1.0', now(),
         'real', 'team-v2.0', 'product:v2');

    if exists (
        select 1 from analytics.product_player_diagnostic_findings_v2
        where diagnostic_code = 'contract-smoke-on-real-id'
    ) then
        raise exception 'smoke diagnostic leaked into product via a real entity id';
    end if;
    if exists (
        select 1 from analytics.product_player_diagnostic_findings_v2
        where diagnostic_code = 'contract-v1-source-on-real-v2'
    ) then
        raise exception 'V1-sourced diagnostic leaked into product via a real V2 entity';
    end if;
    if exists (
        select 1 from analytics.product_player_diagnostic_findings_v2
        where diagnostic_code = 'contract-stale-scope'
    ) then
        raise exception 'stale-scope diagnostic leaked into the active product context';
    end if;
    if not exists (
        select 1 from analytics.product_player_diagnostic_findings_v2
        where diagnostic_code = 'contract-real-player-v2' and entity_id = real_player_id
    ) then
        raise exception 'explicitly real player-v2.0 finding did not surface';
    end if;
    if not exists (
        select 1 from analytics.product_team_diagnostic_findings_v2
        where diagnostic_code = 'contract-real-team-v2' and entity_id = real_team_id
    ) then
        raise exception 'explicitly real team-v2.0 finding did not surface';
    end if;
end;
$$;

rollback;
