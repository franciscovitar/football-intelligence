\set ON_ERROR_STOP on

begin;

insert into public.competitions (id, slug, name, country_code, competition_type, active)
values ('81000000-0000-0000-0000-000000000001', 'match-smoke-league', 'Match Smoke League', 'ZZ', 'LEAGUE', true);

insert into public.seasons (id, competition_id, label, start_date, end_date, status)
values (
  '81000000-0000-0000-0000-000000000002',
  '81000000-0000-0000-0000-000000000001',
  '2026/27',
  '2026-08-01',
  '2027-05-31',
  'ACTIVE'
);

insert into public.rounds (id, season_id, label, sequence, start_date, end_date)
values (
  '81000000-0000-0000-0000-000000000003',
  '81000000-0000-0000-0000-000000000002',
  'Jornada Smoke',
  1,
  '2026-08-29',
  '2026-08-29'
);

insert into public.teams (id, slug, name, short_name, country_code)
values
  ('81000000-0000-0000-0000-000000000010', 'match-smoke-home', 'Match Smoke Home', 'Smoke Home', 'ZZ'),
  ('81000000-0000-0000-0000-000000000011', 'match-smoke-away', 'Match Smoke Away', 'Smoke Away', 'ZZ');

insert into public.players (id, slug, display_name)
values
  ('81000000-0000-0000-0000-000000000020', 'match-smoke-home-player', 'Smoke Home Player'),
  ('81000000-0000-0000-0000-000000000021', 'match-smoke-away-player', 'Smoke Away Player');

insert into public.managers (id, slug, display_name)
values
  ('81000000-0000-0000-0000-000000000030', 'match-smoke-home-manager', 'Smoke Home Manager'),
  ('81000000-0000-0000-0000-000000000031', 'match-smoke-away-manager', 'Smoke Away Manager');

insert into public.sources (id, name, source_type, domain, base_url, active)
values (
  '81000000-0000-0000-0000-000000000040',
  'Match Smoke Provider',
  'STRUCTURED_PROVIDER',
  'example.com',
  'https://example.com',
  true
);

insert into public.source_documents (
  id, source_id, url, normalized_url, title, author_text, retrieved_at, document_type
)
values (
  '81000000-0000-0000-0000-000000000041',
  '81000000-0000-0000-0000-000000000040',
  'https://example.com/match-smoke',
  'https://example.com/match-smoke',
  'Match Smoke Source',
  'Smoke Reporter',
  now(),
  'MATCH_REPORT'
);

insert into public.matches (
  id, external_identity_key, season_id, round_id, home_team_id, away_team_id,
  kickoff_at, status, home_goals, away_goals, venue, attendance, referee,
  identity_verified
)
values (
  '81000000-0000-0000-0000-000000000050',
  'match-smoke:2026-08-29:home:away',
  '81000000-0000-0000-0000-000000000002',
  '81000000-0000-0000-0000-000000000003',
  '81000000-0000-0000-0000-000000000010',
  '81000000-0000-0000-0000-000000000011',
  '2026-08-29T18:00:00Z',
  'FINAL',
  2,
  1,
  'Smoke Stadium',
  12345,
  'Smoke Referee',
  true
);

insert into public.research_runs (
  id, run_key, run_type, target_type, target_id, match_id, started_at, completed_at,
  methodology_sha, search_protocol_version, output_contract_version,
  rating_scale_version, benchmark_version, data_cutoff, status, qa_status
)
values (
  '81000000-0000-0000-0000-000000000060',
  'match-smoke-run-v1',
  'MATCH_REVIEW',
  'MATCH',
  '81000000-0000-0000-0000-000000000050',
  '81000000-0000-0000-0000-000000000050',
  now(),
  now(),
  'smoke-methodology-sha',
  'SEARCH_PROTOCOL_V2',
  'OUTPUT_CONTRACT_V2',
  'MATCH_RATING_SCALE_V1',
  'MATCH_BENCHMARKS_V1.0',
  now(),
  'PUBLISHED',
  'PASS'
);

insert into public.player_appearances (
  match_id, player_id, team_id, starter, minute_on, minute_off, minutes,
  broad_position, role_label, role_confidence
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000020',
    '81000000-0000-0000-0000-000000000010',
    true, 0, 90, 90, 'FW', 'Extremo creador', 90
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000021',
    '81000000-0000-0000-0000-000000000011',
    true, 0, 90, 90, 'FW', 'Delantero móvil', 90
  );

insert into public.team_match_stats (
  match_id, team_id, goals, xg, shots, shots_on_target, possession_pct,
  big_chances, box_touches, corners, extra_stats, provider_source_id,
  provider_model, definition_version, evidence_class, retrieved_at
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000010',
    2, 2.20, 14, 6, 58, 4, 31, 7, '{"xA": 1.55}'::jsonb,
    '81000000-0000-0000-0000-000000000040', 'smoke-xg', 'v1',
    'PROVIDER_DERIVED', now()
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000011',
    1, 0.80, 7, 2, 42, 1, 14, 3, '{"xA": 0.60}'::jsonb,
    '81000000-0000-0000-0000-000000000040', 'smoke-xg', 'v1',
    'PROVIDER_DERIVED', now()
  );

insert into public.player_match_stats (
  match_id, player_id, team_id, minutes, goals, assists, xg, xa, shots,
  shots_on_target, chances_created, extra_stats, provider_source_id,
  provider_model, definition_version, evidence_class, retrieved_at
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000020',
    '81000000-0000-0000-0000-000000000010',
    90, 1, 1, 0.65, 0.75, 4, 2, 4, '{"provider_rating": 8.4}'::jsonb,
    '81000000-0000-0000-0000-000000000040', 'smoke-player', 'v1',
    'PROVIDER_DERIVED', now()
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000021',
    '81000000-0000-0000-0000-000000000011',
    90, 1, 0, 0.55, 0.10, 3, 1, 1, '{"provider_rating": 6.7}'::jsonb,
    '81000000-0000-0000-0000-000000000040', 'smoke-player', 'v1',
    'PROVIDER_DERIVED', now()
  );

insert into public.match_reviews (
  match_id, research_run_id, review_version, summary, key_takeaways,
  evidence_mix, methodology_sha, rating_scale_version, benchmark_version,
  status, published_at
)
values (
  '81000000-0000-0000-0000-000000000050',
  '81000000-0000-0000-0000-000000000060',
  1,
  'Smoke Home controló mejor el partido y produjo ocasiones de mayor calidad. La lectura está persistida y Next.js sólo la presenta.',
  '["El proceso ofensivo local fue superior.","El visitante compitió pero generó menos peligro."]'::jsonb,
  jsonb_build_object('source_document_ids', jsonb_build_array('81000000-0000-0000-0000-000000000041')),
  'smoke-methodology-sha',
  'MATCH_RATING_SCALE_V1',
  'MATCH_BENCHMARKS_V1.0',
  'PUBLISHED',
  now()
);

insert into public.team_match_reviews (
  match_id, team_id, research_run_id, review_version, facts_score, expert_score,
  fan_score, final_score, confidence, evidence_status, facts_coverage,
  expert_coverage, fan_coverage, tactical_coverage, attack_score, creation_score,
  control_score, defence_score, pressing_score, offensive_transition_score,
  defensive_transition_score, summary, strengths, concerns, methodology_sha,
  rating_scale_version, benchmark_version, status, published_at
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000010',
    '81000000-0000-0000-0000-000000000060',
    1, 8.1, 8.0, 7.8, 8.1, 88, 'TRIANGULATED_ESTIMATE', 90, 70, 55, 70,
    8.2, 8.1, 8.0, 7.4, 7.2, 7.8, 7.0,
    'Smoke Home produjo el mejor proceso colectivo.',
    '["Creó mejores ocasiones","Controló el territorio"]'::jsonb,
    '["Concedió una transición peligrosa"]'::jsonb,
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000011',
    '81000000-0000-0000-0000-000000000060',
    1, 5.7, 5.9, 6.0, 5.8, 82, 'TRIANGULATED_ESTIMATE', 90, 65, 50, 65,
    5.5, 5.4, 5.6, 6.0, 5.8, 5.9, 5.6,
    'Smoke Away compitió, pero su proceso ofensivo fue inferior.',
    '["Mantuvo el partido abierto"]'::jsonb,
    '["Generó pocas ocasiones de calidad"]'::jsonb,
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  );

insert into public.manager_match_reviews (
  match_id, manager_id, team_id, research_run_id, review_version, facts_score,
  expert_score, fan_score, final_score, confidence, evidence_status,
  initial_plan_score, adaptation_score, substitutions_score, initial_plan,
  adjustments, what_worked, what_failed, summary, methodology_sha,
  rating_scale_version, benchmark_version, status, published_at
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000030',
    '81000000-0000-0000-0000-000000000010',
    '81000000-0000-0000-0000-000000000060',
    1, 7.8, 7.9, 7.6, 7.9, 80, 'TRIANGULATED_ESTIMATE', 8.0, 7.8, 7.7,
    'Plan local de control y amplitud.', 'Ajustó alturas para proteger la ventaja.',
    '["Control territorial"]'::jsonb, '["Una transición concedida"]'::jsonb,
    'Smoke Home Manager ayudó a sostener el mejor proceso.',
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000031',
    '81000000-0000-0000-0000-000000000011',
    '81000000-0000-0000-0000-000000000060',
    1, 5.9, 6.0, 6.0, 5.9, 72, 'TRIANGULATED_ESTIMATE', 6.2, 5.7, 5.8,
    'Plan visitante de bloque medio y salida rápida.', 'Intentó ganar altura tras el descanso.',
    '["El equipo siguió en partido"]'::jsonb, '["No corrigió la baja creación"]'::jsonb,
    'Smoke Away Manager sostuvo competitividad sin resolver el déficit ofensivo.',
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  );

insert into public.player_match_reviews (
  match_id, player_id, team_id, research_run_id, review_version, facts_score,
  expert_score, fan_score, final_score, confidence, evidence_status,
  facts_coverage, expert_coverage, fan_coverage, tactical_coverage, role_label,
  summary, positive_notes, negative_notes, methodology_sha,
  rating_scale_version, benchmark_version, status, published_at
)
values
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000020',
    '81000000-0000-0000-0000-000000000010',
    '81000000-0000-0000-0000-000000000060',
    1, 8.6, 8.4, 8.2, 8.5, 90, 'TRIANGULATED_ESTIMATE', 95, 70, 55, 70,
    'Extremo creador',
    'Smoke Home Player fue decisivo y además sostuvo un proceso creativo fuerte.',
    '["Gol y asistencia","Creación recurrente"]'::jsonb,
    '["Una pérdida en transición"]'::jsonb,
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  ),
  (
    '81000000-0000-0000-0000-000000000050',
    '81000000-0000-0000-0000-000000000021',
    '81000000-0000-0000-0000-000000000011',
    '81000000-0000-0000-0000-000000000060',
    1, 6.7, 6.5, 6.6, 6.6, 82, 'TRIANGULATED_ESTIMATE', 95, 65, 50, 60,
    'Delantero móvil',
    'Smoke Away Player convirtió, aunque participó menos en un ataque de baja producción.',
    '["Finalización del gol"]'::jsonb,
    '["Poca creación propia"]'::jsonb,
    'smoke-methodology-sha', 'MATCH_RATING_SCALE_V1', 'MATCH_BENCHMARKS_V1.0',
    'PUBLISHED', now()
  );

commit;
