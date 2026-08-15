\set ON_ERROR_STOP on

begin;

alter table analytics.player_feature_snapshots
    add column metric_granularity text,
    add column percentile_state text;

update analytics.player_feature_snapshots
set metric_granularity = case
        when model_version = 'player-v2.0'
         and role = 'goalkeeper'
         and metric_name in (
            'average_distance_from_goal',
            'claims',
            'clean_sheets',
            'crosses_stopped',
            'distribution_accuracy_pct',
            'goals_conceded',
            'goals_prevented',
            'launches',
            'long_passes',
            'passes',
            'psxg',
            'save_pct',
            'saves',
            'shots_on_target_faced',
            'sweeper_actions',
            'xg_on_target_faced'
         ) then 'goalkeeper_match'
        else 'player_match'
    end,
    percentile_state = case
        when percentile is null then 'not_applicable'
        else 'ready'
    end;

alter table analytics.player_feature_snapshots
    alter column metric_granularity set not null,
    alter column metric_granularity set default 'player_match',
    alter column percentile_state set not null,
    alter column percentile_state set default 'ready';

alter table analytics.player_feature_snapshots
    drop constraint player_feature_snapshots_pkey,
    add primary key (
        player_id,
        scope_key,
        window_key,
        metric_name,
        model_version,
        metric_granularity
    ),
    drop constraint player_feature_snapshots_reference_sample_check,
    add constraint player_feature_snapshots_reference_sample_check
        check (reference_sample_size >= 0),
    add constraint player_feature_snapshots_metric_granularity_check
        check (
            metric_granularity in (
                'player_match',
                'player_season',
                'goalkeeper_match',
                'goalkeeper_season'
            )
        ),
    add constraint player_feature_snapshots_percentile_state_check
        check (
            percentile_state in ('ready', 'insufficient_sample', 'not_applicable')
            and (percentile_state <> 'ready' or percentile is not null)
            and (percentile_state = 'ready' or percentile is null)
        );

alter table analytics.player_score_snapshots
    drop constraint player_score_snapshots_reference_sample_check,
    add constraint player_score_snapshots_reference_sample_check
        check (reference_sample_size >= 0);

commit;
