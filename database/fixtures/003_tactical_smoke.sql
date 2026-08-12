\set ON_ERROR_STOP on

insert into football.team_match_lineups (
    match_id, team_id, formation, coach_name
)
select
    m.id,
    t.id,
    case
        when t.name = 'Web Smoke United' then '4-3-3'
        else '4-4-2'
    end,
    case
        when t.name = 'Web Smoke United' then 'Web Smoke Coach A'
        else 'Web Smoke Coach B'
    end
from football.matches as m
join football.seasons as s on s.id = m.season_id
join football.competitions as c on c.id = s.competition_id
join football.teams as t
  on t.id in (m.home_team_id, m.away_team_id)
where c.code = 'ENG_PL'
  and s.label = 'web-smoke'
  and t.name in ('Web Smoke United', 'Web Smoke City')
on conflict (match_id, team_id) do update
set
    formation = excluded.formation,
    coach_name = excluded.coach_name,
    updated_at = now();
