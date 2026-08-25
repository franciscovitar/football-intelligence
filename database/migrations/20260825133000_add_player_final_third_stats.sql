\set ON_ERROR_STOP on

begin;

alter table football.player_match_stats
    add column passes_into_final_third smallint,
    add constraint player_match_stats_passes_into_final_third_check
        check (passes_into_final_third is null or passes_into_final_third >= 0),
    add constraint player_match_stats_passes_into_final_third_subset_check
        check (
            passes_into_final_third is null
            or passes_total is null
            or passes_into_final_third <= passes_total
        );

commit;
