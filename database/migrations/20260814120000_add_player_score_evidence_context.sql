\set ON_ERROR_STOP on

begin;

alter table analytics.player_score_snapshots
    alter column overall_score drop not null,
    add column position_family text,
    add column data_context text not null default 'real',
    add column evidence_weight_available numeric(10, 6) not null default 1,
    add column evidence_weight_required numeric(10, 6) not null default 1,
    add column evidence_coverage_pct numeric(5, 2) not null default 100,
    add column evidence_state text not null default 'ready',
    add column evidence_metrics_available text[] not null default '{}'::text[],
    add column evidence_metrics_required text[] not null default '{}'::text[];

alter table analytics.player_score_snapshots
    add constraint player_score_snapshots_data_context_check
        check (data_context in ('real', 'test_smoke')),
    add constraint player_score_snapshots_evidence_weights_check
        check (
            evidence_weight_available >= 0
            and evidence_weight_required >= 0
            and evidence_weight_available <= evidence_weight_required
        ),
    add constraint player_score_snapshots_evidence_coverage_check
        check (evidence_coverage_pct between 0 and 100),
    add constraint player_score_snapshots_evidence_state_check
        check (evidence_state in ('ready', 'partial', 'insufficient_data'));

create index player_score_snapshots_product_context_idx
    on analytics.player_score_snapshots (
        data_context,
        evidence_state,
        scope_key,
        window_key,
        model_version,
        overall_score desc
    );

create view analytics.product_player_score_snapshots as
select *
from analytics.player_score_snapshots
where data_context = 'real'
  and model_version = 'player-v2.0'
  and evidence_state = 'ready'
  and overall_score is not null;

revoke all on analytics.product_player_score_snapshots from public;

commit;
