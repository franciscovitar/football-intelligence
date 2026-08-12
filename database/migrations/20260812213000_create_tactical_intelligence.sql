\set ON_ERROR_STOP on

begin;

create table football.team_match_lineups (
    match_id bigint not null
        references football.matches(id) on delete cascade,
    team_id bigint not null
        references football.teams(id) on delete restrict,
    formation text,
    coach_name text,
    updated_at timestamptz not null default now(),
    primary key (match_id, team_id),
    constraint team_match_lineups_formation_check
        check (
            formation is null
            or formation ~ '^[0-9]+(-[0-9]+){2,4}$'
        ),
    constraint team_match_lineups_coach_not_blank_check
        check (coach_name is null or btrim(coach_name) <> '')
);

create index team_match_lineups_team_match_idx
    on football.team_match_lineups (team_id, match_id);

create trigger team_match_lineups_match_team_check
before insert or update of match_id, team_id
on football.team_match_lineups
for each row
execute function football.enforce_match_team_membership();

create table analytics.team_tactical_snapshots (
    team_id bigint not null
        references football.teams(id) on delete cascade,
    season_id bigint not null
        references football.seasons(id) on delete cascade,
    scope_key text not null,
    matches smallint not null,
    source_confidence numeric(6, 5) not null,
    control_score numeric(5, 2),
    attacking_volume_score numeric(5, 2),
    defensive_resistance_score numeric(5, 2),
    style_signal text not null,
    defensive_signal text not null,
    primary_formation text,
    formation_matches smallint not null,
    formation_share numeric(6, 5),
    formation_confidence numeric(6, 5) not null,
    formation_signal text not null,
    alternative_formations jsonb not null default '[]'::jsonb,
    tactical_confidence numeric(6, 5) not null,
    summary text not null,
    evidence jsonb not null default '{}'::jsonb,
    source_model_version text not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (team_id, scope_key, model_version),
    constraint team_tactical_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint team_tactical_matches_check
        check (matches > 0),
    constraint team_tactical_source_confidence_check
        check (source_confidence between 0 and 1),
    constraint team_tactical_control_score_check
        check (control_score is null or control_score between 0 and 100),
    constraint team_tactical_attacking_volume_score_check
        check (
            attacking_volume_score is null
            or attacking_volume_score between 0 and 100
        ),
    constraint team_tactical_defensive_resistance_score_check
        check (
            defensive_resistance_score is null
            or defensive_resistance_score between 0 and 100
        ),
    constraint team_tactical_style_signal_check
        check (
            style_signal in (
                'control_and_volume',
                'possession_control',
                'volume_without_control',
                'low_control_low_volume',
                'balanced',
                'insufficient_evidence'
            )
        ),
    constraint team_tactical_defensive_signal_check
        check (
            defensive_signal in (
                'restrictive_shot_profile',
                'balanced',
                'permissive_shot_profile',
                'insufficient_evidence'
            )
        ),
    constraint team_tactical_primary_formation_check
        check (
            primary_formation is null
            or primary_formation ~ '^[0-9]+(-[0-9]+){2,4}$'
        ),
    constraint team_tactical_formation_matches_check
        check (formation_matches between 0 and matches),
    constraint team_tactical_formation_share_check
        check (
            (formation_matches = 0 and formation_share is null)
            or (
                formation_matches > 0
                and formation_share between 0 and 1
            )
        ),
    constraint team_tactical_formation_confidence_check
        check (formation_confidence between 0 and 1),
    constraint team_tactical_formation_signal_check
        check (
            formation_signal in (
                'stable',
                'variable',
                'mixed',
                'limited_evidence',
                'unavailable'
            )
        ),
    constraint team_tactical_alternatives_array_check
        check (jsonb_typeof(alternative_formations) = 'array'),
    constraint team_tactical_confidence_check
        check (tactical_confidence between 0 and 1),
    constraint team_tactical_summary_not_blank_check
        check (btrim(summary) <> ''),
    constraint team_tactical_evidence_object_check
        check (jsonb_typeof(evidence) = 'object'),
    constraint team_tactical_source_model_not_blank_check
        check (btrim(source_model_version) <> ''),
    constraint team_tactical_model_not_blank_check
        check (btrim(model_version) <> '')
);

create index team_tactical_scope_signal_idx
    on analytics.team_tactical_snapshots (
        scope_key,
        model_version,
        style_signal,
        tactical_confidence desc
    );

create index team_tactical_formation_idx
    on analytics.team_tactical_snapshots (
        scope_key,
        model_version,
        primary_formation,
        formation_confidence desc
    );

revoke all on football.team_match_lineups from public;
revoke all on analytics.team_tactical_snapshots from public;

commit;
