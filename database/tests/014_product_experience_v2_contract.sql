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
end;
$$;

rollback;
