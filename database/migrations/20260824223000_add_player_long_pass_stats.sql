\set ON_ERROR_STOP on

begin;

alter table football.player_match_stats
    add column long_passes_accurate smallint,
    add constraint player_match_stats_long_passes_accurate_check
        check (long_passes_accurate is null or long_passes_accurate >= 0),
    add constraint player_match_stats_long_passes_accurate_subset_check
        check (
            long_passes_accurate is null
            or passes_accurate is null
            or long_passes_accurate <= passes_accurate
        );

commit;
