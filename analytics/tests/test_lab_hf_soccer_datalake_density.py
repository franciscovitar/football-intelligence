from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


AUDIT_SCRIPT = r'''
import pathlib
import urllib.request

import duckdb

root = pathlib.Path("/tmp/fi_hf_density")
root.mkdir(parents=True, exist_ok=True)
base = "https://huggingface.co/datasets/eatpizzanot/soccer-dataset/resolve/main"
for table in ("leagues", "fixtures", "fixture_players", "fixture_players_stats_flat"):
    target = root / f"{table}.parquet"
    if not target.exists():
        with urllib.request.urlopen(f"{base}/{table}.parquet", timeout=120) as response:
            target.write_bytes(response.read())

con = duckdb.connect()
con.execute("PRAGMA threads=4")
con.execute(f"""
CREATE TEMP TABLE target_leagues AS
SELECT
  id AS dataset_league_id,
  api_football_id,
  CASE api_football_id
    WHEN 128 THEN 'ARG_LPF'
    WHEN 39 THEN 'ENG_PL'
    WHEN 140 THEN 'ESP_LL'
    WHEN 135 THEN 'ITA_SA'
    WHEN 78 THEN 'GER_BL1'
    WHEN 61 THEN 'FRA_L1'
  END AS competition_code,
  name,
  country
FROM read_parquet('{(root / "leagues.parquet").as_posix()}')
WHERE api_football_id IN (128, 39, 140, 135, 78, 61)
""")

mapping = con.execute("""
SELECT competition_code, api_football_id, dataset_league_id, name, country
FROM target_leagues
ORDER BY competition_code
""").fetchall()
if len(mapping) != 6:
    raise RuntimeError(f"expected six target leagues, got {mapping!r}")

con.execute(f"""
CREATE TEMP TABLE target_fixtures AS
SELECT
  f.id AS fixture_id,
  tl.competition_code,
  EXTRACT(year FROM f.date_utc)::INTEGER AS calendar_year,
  f.is_played
FROM read_parquet('{(root / "fixtures.parquet").as_posix()}') f
JOIN target_leagues tl ON tl.dataset_league_id = f.league_id
WHERE EXTRACT(year FROM f.date_utc) BETWEEN 2016 AND 2021
""")

con.execute(f"""
CREATE TEMP TABLE target_fp AS
SELECT
  tf.competition_code,
  tf.calendar_year,
  fp.fixture_id,
  fp.player_id,
  fp.minutes,
  fp.rating
FROM read_parquet('{(root / "fixture_players.parquet").as_posix()}') fp
JOIN target_fixtures tf ON tf.fixture_id = fp.fixture_id
""")

con.execute(f"""
CREATE TEMP TABLE target_stats AS
SELECT
  tf.competition_code,
  tf.calendar_year,
  s.fixture_id,
  s.player_id,
  s.games_minutes,
  s.games_rating,
  s.goals_total,
  s.goals_assists,
  s.passes_total,
  s.passes_accuracy,
  s.passes_key,
  s.duels_total,
  s.duels_won,
  s.tackles_total,
  s.tackles_interceptions,
  s.tackles_blocks,
  s.dribbles_attempts,
  s.dribbles_success,
  s.shots_total,
  s.shots_on,
  s.fouls_committed,
  s.fouls_drawn
FROM read_parquet('{(root / "fixture_players_stats_flat.parquet").as_posix()}') s
JOIN target_fixtures tf ON tf.fixture_id = s.fixture_id
""")

rows = con.execute("""
WITH base AS (
  SELECT competition_code, calendar_year,
         COUNT(*) FILTER (WHERE is_played) AS played
  FROM target_fixtures GROUP BY 1,2
), fp AS (
  SELECT competition_code, calendar_year,
         COUNT(*) AS fp_rows,
         COUNT(DISTINCT fixture_id) AS fp_fixtures,
         COUNT(DISTINCT player_id) AS players
  FROM target_fp GROUP BY 1,2
), st AS (
  SELECT competition_code, calendar_year,
         COUNT(*) AS stat_rows,
         COUNT(DISTINCT fixture_id) AS stat_fixtures,
         COUNT(*) FILTER (WHERE games_minutes IS NOT NULL) AS minutes_n,
         COUNT(*) FILTER (WHERE games_rating IS NOT NULL) AS rating_n,
         COUNT(*) FILTER (WHERE goals_assists IS NOT NULL) AS assists_n,
         COUNT(*) FILTER (WHERE passes_total IS NOT NULL) AS passes_n,
         COUNT(*) FILTER (WHERE duels_total IS NOT NULL) AS duels_n,
         COUNT(*) FILTER (WHERE tackles_total IS NOT NULL) AS tackles_n,
         COUNT(*) FILTER (WHERE shots_total IS NOT NULL) AS shots_n
  FROM target_stats GROUP BY 1,2
)
SELECT b.competition_code, b.calendar_year, b.played,
       ROUND(100.0 * COALESCE(fp.fp_fixtures,0) / NULLIF(b.played,0),1) AS fp_fx_pct,
       ROUND(100.0 * COALESCE(st.stat_fixtures,0) / NULLIF(b.played,0),1) AS stat_fx_pct,
       ROUND(1.0 * COALESCE(fp.fp_rows,0) / NULLIF(fp.fp_fixtures,0),1) AS player_rows_per_fx,
       COALESCE(fp.players,0) AS players,
       ROUND(100.0 * COALESCE(st.minutes_n,0) / NULLIF(st.stat_rows,0),1) AS minutes_pct,
       ROUND(100.0 * COALESCE(st.rating_n,0) / NULLIF(st.stat_rows,0),1) AS rating_pct,
       ROUND(100.0 * COALESCE(st.assists_n,0) / NULLIF(st.stat_rows,0),1) AS assists_pct,
       ROUND(100.0 * COALESCE(st.passes_n,0) / NULLIF(st.stat_rows,0),1) AS passes_pct,
       ROUND(100.0 * COALESCE(st.duels_n,0) / NULLIF(st.stat_rows,0),1) AS duels_pct,
       ROUND(100.0 * COALESCE(st.tackles_n,0) / NULLIF(st.stat_rows,0),1) AS tackles_pct,
       ROUND(100.0 * COALESCE(st.shots_n,0) / NULLIF(st.stat_rows,0),1) AS shots_pct
FROM base b
LEFT JOIN fp USING (competition_code, calendar_year)
LEFT JOIN st USING (competition_code, calendar_year)
ORDER BY 1,2
""").fetchall()

if len(rows) != 36:
    raise RuntimeError(f"expected 36 league-year rows, got {len(rows)}")

overall = con.execute("""
WITH base AS (
  SELECT competition_code, COUNT(*) FILTER (WHERE is_played) AS played
  FROM target_fixtures GROUP BY 1
), fp AS (
  SELECT competition_code, COUNT(*) AS fp_rows,
         COUNT(DISTINCT fixture_id) AS fp_fixtures,
         COUNT(DISTINCT player_id) AS players
  FROM target_fp GROUP BY 1
), st AS (
  SELECT competition_code, COUNT(*) AS stat_rows,
         COUNT(DISTINCT fixture_id) AS stat_fixtures,
         COUNT(*) FILTER (WHERE games_minutes IS NOT NULL) AS minutes_n,
         COUNT(*) FILTER (WHERE games_rating IS NOT NULL) AS rating_n,
         COUNT(*) FILTER (WHERE goals_assists IS NOT NULL) AS assists_n,
         COUNT(*) FILTER (WHERE passes_total IS NOT NULL) AS passes_n,
         COUNT(*) FILTER (WHERE duels_total IS NOT NULL) AS duels_n,
         COUNT(*) FILTER (WHERE tackles_total IS NOT NULL) AS tackles_n,
         COUNT(*) FILTER (WHERE shots_total IS NOT NULL) AS shots_n
  FROM target_stats GROUP BY 1
)
SELECT b.competition_code, b.played,
       ROUND(100.0 * fp.fp_fixtures / NULLIF(b.played,0),1),
       ROUND(100.0 * st.stat_fixtures / NULLIF(b.played,0),1),
       ROUND(1.0 * fp.fp_rows / NULLIF(fp.fp_fixtures,0),1),
       fp.players,
       ROUND(100.0 * st.minutes_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.rating_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.assists_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.passes_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.duels_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.tackles_n / NULLIF(st.stat_rows,0),1),
       ROUND(100.0 * st.shots_n / NULLIF(st.stat_rows,0),1)
FROM base b JOIN fp USING (competition_code) JOIN st USING (competition_code)
ORDER BY 1
""").fetchall()

print("MAPPING|code|api_id|dataset_id|name|country")
for row in mapping:
    print("MAPPING|" + "|".join(str(value) for value in row))
print("YEAR|code|year|played|player_fx_pct|stat_fx_pct|rows_per_fx|players|minutes_pct|rating_pct|assists_pct|passes_pct|duels_pct|tackles_pct|shots_pct")
for row in rows:
    print("YEAR|" + "|".join(str(value) for value in row))
print("OVERALL|code|played|player_fx_pct|stat_fx_pct|rows_per_fx|players|minutes_pct|rating_pct|assists_pct|passes_pct|duels_pct|tackles_pct|shots_pct")
for row in overall:
    print("OVERALL|" + "|".join(str(value) for value in row))
'''


def test_hf_soccer_datalake_player_density_spike() -> None:
    result = subprocess.run(
        ["uv", "run", "--with", "duckdb", "python", "-c", AUDIT_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    pytest.fail("technical-spike evidence follows:\n" + result.stdout)
