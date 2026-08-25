\set ON_ERROR_STOP on

begin;

alter table football.player_match_stats
    add column aerial_duels smallint,
    add column aerial_duels_won smallint,
    add constraint player_match_stats_aerial_duels_check
        check (aerial_duels is null or aerial_duels >= 0),
    add constraint player_match_stats_aerial_duels_won_check
        check (aerial_duels_won is null or aerial_duels_won >= 0),
    add constraint player_match_stats_aerial_duels_consistency_check
        check (
            aerial_duels_won is null
            or aerial_duels is null
            or aerial_duels_won <= aerial_duels
        );

commit;
