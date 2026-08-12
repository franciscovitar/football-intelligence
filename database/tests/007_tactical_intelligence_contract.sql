\set ON_ERROR_STOP on

begin;

do $$
declare
    competition_id_value bigint;
    season_id_value bigint;
    home_id bigint;
    away_id bigint;
    match_id_value bigint;
begin
    if to_regclass('football.team_match_lineups') is null then
        raise exception 'team_match_lineups table is missing';
    end if;
    if to_regclass('analytics.team_tactical_snapshots') is null then
        raise exception 'team_tactical_snapshots table is missing';
    end if;

    select id into competition_id_value
    from football.competitions
    where code = 'ENG_PL';

    insert into football.seasons (competition_id, label)
    values (competition_id_value, 'tactical-contract')
    returning id into season_id_value;

    insert into football.teams (name)
    values ('Tactical Contract Home')
    returning id into home_id;

    insert into football.teams (name)
    values ('Tactical Contract Away')
    returning id into away_id;

    insert into football.matches (
        season_id, home_team_id, away_team_id,
        status, home_score, away_score
    )
    values (
        season_id_value, home_id, away_id,
        'finished', 1, 0
    )
    returning id into match_id_value;

    insert into football.team_match_lineups (
        match_id, team_id, formation, coach_name
    )
    values (
        match_id_value, home_id, '4-3-3', 'Contract Coach'
    );

    insert into analytics.team_tactical_snapshots (
        team_id, season_id, scope_key, matches,
        source_confidence,
        control_score, attacking_volume_score,
        defensive_resistance_score,
        style_signal, defensive_signal,
        primary_formation, formation_matches,
        formation_share, formation_confidence, formation_signal,
        alternative_formations,
        tactical_confidence, summary, evidence,
        source_model_version, model_version, calculated_at
    )
    values (
        home_id, season_id_value, 'competition:ENG_PL:tactical-contract', 4,
        0.80,
        75, 70, 68,
        'control_and_volume', 'restrictive_shot_profile',
        '4-3-3', 3,
        0.75, 0.70, 'stable',
        '[{"formation":"4-3-3","matches":3,"share":0.75}]'::jsonb,
        0.78, 'Contract tactical summary.',
        '{"source_dimensions":{"control":75}}'::jsonb,
        'team-v1.0', 'tactical-v1.0', now()
    );

    begin
        update analytics.team_tactical_snapshots
        set style_signal = 'high_press'
        where team_id = home_id
          and scope_key = 'competition:ENG_PL:tactical-contract'
          and model_version = 'tactical-v1.0';
        raise exception 'expected unsupported tactical signal to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into football.team_match_lineups (
            match_id, team_id, formation
        )
        values (
            match_id_value, away_id, 'press-high'
        );
        raise exception 'expected invalid nominal formation to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
