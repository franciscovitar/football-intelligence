\set ON_ERROR_STOP on

begin;

alter table analytics.player_feature_snapshots
    add column data_context text;

update analytics.player_feature_snapshots as feature
set data_context = coalesce(
    (
        select score.data_context
        from analytics.player_score_snapshots as score
        where score.player_id = feature.player_id
          and score.scope_key = feature.scope_key
          and score.window_key = feature.window_key
          and score.model_version = feature.model_version
        limit 1
    ),
    'real'
);

alter table analytics.player_feature_snapshots
    alter column data_context set not null,
    alter column data_context set default 'real',
    add constraint player_feature_snapshots_data_context_check
        check (data_context in ('real', 'test_smoke'));

alter table analytics.team_feature_snapshots
    add column data_context text not null default 'real',
    add constraint team_feature_snapshots_data_context_check
        check (data_context in ('real', 'test_smoke'));

alter table analytics.team_score_snapshots
    add column data_context text not null default 'real',
    add constraint team_score_snapshots_data_context_check
        check (data_context in ('real', 'test_smoke'));

create index player_feature_snapshots_product_context_idx
    on analytics.player_feature_snapshots (
        data_context,
        scope_key,
        window_key,
        model_version,
        player_id
    );

create index team_score_snapshots_product_context_idx
    on analytics.team_score_snapshots (
        data_context,
        scope_key,
        window_key,
        model_version,
        evidence_state,
        confidence desc
    );

create view analytics.product_player_detail_v2 as
select *
from analytics.player_score_snapshots
where data_context = 'real'
  and model_version = 'player-v2.0';

create view analytics.product_player_ranking_candidates_v2 as
select *
from analytics.product_player_detail_v2
where confidence >= 0.40
  and minutes >= case window_key
        when 'last_3' then 90
        when 'last_5' then 180
        when 'last_10' then 270
        when 'season' then 450
        else 2147483647
      end;

create view analytics.product_team_detail_v2 as
select *
from analytics.team_score_snapshots
where data_context = 'real'
  and model_version = 'team-v2.0';

create view analytics.product_team_ranking_candidates_v2 as
select *
from analytics.product_team_detail_v2
where confidence >= 0.40;

create table analytics.player_watchlist_entries (
    player_id bigint primary key
        references football.players(id) on delete cascade,
    category text not null default 'manual',
    reason text,
    created_at timestamptz not null default now(),
    constraint player_watchlist_entries_category_check
        check (
            category in (
                'manual',
                'emerging',
                'regression_watch',
                'underperforming_process'
            )
        ),
    constraint player_watchlist_entries_reason_check
        check (reason is null or (btrim(reason) <> '' and length(reason) <= 500))
);

create view analytics.product_player_watchlist_v2 as
select
    entry.player_id,
    entry.category,
    entry.reason,
    entry.created_at
from analytics.player_watchlist_entries as entry
where exists (
    select 1
    from analytics.product_player_detail_v2 as detail
    where detail.player_id = entry.player_id
);

revoke all on analytics.product_player_detail_v2 from public;
revoke all on analytics.product_player_ranking_candidates_v2 from public;
revoke all on analytics.product_team_detail_v2 from public;
revoke all on analytics.product_team_ranking_candidates_v2 from public;
revoke all on analytics.player_watchlist_entries from public;
revoke all on analytics.product_player_watchlist_v2 from public;

commit;
