begin;

insert into ingestion.providers (code, display_name)
values ('api-football', 'API-Football')
on conflict (code) do update
set
    display_name = excluded.display_name,
    is_active = true;

insert into football.competitions (code, name, country_code, kind)
values
    ('ARG_LPF', 'Liga Profesional', 'ARG', 'league'),
    ('ENG_PL', 'Premier League', 'ENG', 'league'),
    ('ESP_LL', 'LaLiga', 'ESP', 'league'),
    ('ITA_SA', 'Serie A', 'ITA', 'league'),
    ('GER_BL1', 'Bundesliga', 'GER', 'league'),
    ('FRA_L1', 'Ligue 1', 'FRA', 'league')
on conflict (code) do update
set
    name = excluded.name,
    country_code = excluded.country_code,
    kind = excluded.kind,
    is_active = true,
    updated_at = now();

commit;
