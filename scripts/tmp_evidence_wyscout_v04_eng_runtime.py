from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg

SCOPE = "competition:ENG_PL:2017/18"
MODEL = "player-v2.0"


def scalar(connection: psycopg.Connection[Any], query: str, params: tuple[Any, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise RuntimeError("scalar query returned no row")
    return int(row[0])


def fetch_dicts(
    connection: psycopg.Connection[Any], query: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def build_report(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        season_row = connection.execute(
            """
            select s.id
            from football.seasons s
            join football.competitions c on c.id = s.competition_id
            where c.code = 'ENG_PL' and s.label = '2017/18'
            """
        ).fetchone()
        if season_row is None:
            raise RuntimeError("ENG_PL 2017/18 season missing")
        season_id = int(season_row[0])

        canonical = {
            "matches": scalar(
                connection, "select count(*) from football.matches where season_id=%s", (season_id,)
            ),
            "teams": scalar(
                connection,
                """
                select count(distinct team_id) from (
                    select home_team_id as team_id from football.matches where season_id=%s
                    union all
                    select away_team_id as team_id from football.matches where season_id=%s
                ) scoped
                """,
                (season_id, season_id),
            ),
            "players": scalar(
                connection,
                """
                select count(distinct pa.player_id)
                from football.player_appearances pa
                join football.matches m on m.id=pa.match_id
                where m.season_id=%s
                """,
                (season_id,),
            ),
            "player_appearances": scalar(
                connection,
                """
                select count(*) from football.player_appearances pa
                join football.matches m on m.id=pa.match_id
                where m.season_id=%s
                """,
                (season_id,),
            ),
            "player_match_stats": scalar(
                connection,
                """
                select count(*) from football.player_match_stats pms
                join football.matches m on m.id=pms.match_id
                where m.season_id=%s
                """,
                (season_id,),
            ),
            "team_match_stats": scalar(
                connection,
                """
                select count(*) from football.team_match_stats tms
                join football.matches m on m.id=tms.match_id
                where m.season_id=%s
                """,
                (season_id,),
            ),
            "source_observations": scalar(
                connection,
                """
                select count(*)
                from ingestion.source_observations o
                join ingestion.providers p on p.id=o.provider_id
                where p.code='wyscout-open'
                  and o.entity_identity_hints ->> 'season_label'='2017/18'
                  and o.entity_identity_hints ->> 'competition_external_id'='364'
                """,
            ),
        }

        player_match_metric_coverage = fetch_dicts(
            connection,
            """
            select
                count(*) as player_match_rows,
                count(long_passes_accurate) as long_passes_accurate_known,
                count(*) filter (where long_passes_accurate is null) as long_passes_accurate_missing,
                count(*) filter (where long_passes_accurate = 0) as long_passes_accurate_zero,
                count(*) filter (where long_passes_accurate > 0) as long_passes_accurate_positive,
                count(passes_into_final_third) as passes_into_final_third_known,
                count(*) filter (where passes_into_final_third is null) as passes_into_final_third_missing,
                count(*) filter (where passes_into_final_third = 0) as passes_into_final_third_zero,
                count(*) filter (where passes_into_final_third > 0) as passes_into_final_third_positive,
                count(aerial_duels) as aerial_duels_known,
                count(aerial_duels_won) as aerial_duels_won_known,
                count(passes_total) as passes_total_known,
                count(passes_accurate) as passes_accurate_known
            from football.player_match_stats pms
            join football.matches m on m.id=pms.match_id
            where m.season_id=%s
            """,
            (season_id,),
        )[0]

        source_metric_counts = fetch_dicts(
            connection,
            """
            select metric_name, count(*) as observations
            from ingestion.source_observations o
            join ingestion.providers p on p.id=o.provider_id
            where p.code='wyscout-open'
              and o.entity_identity_hints ->> 'season_label'='2017/18'
              and o.entity_identity_hints ->> 'competition_external_id'='364'
              and metric_name in (
                'long_passes_accurate', 'passes_total', 'passes_accurate',
                'aerial_duels', 'aerial_duels_won', 'aerial_duel_win_pct',
                'progressive_passes', 'passes_into_final_third'
              )
            group by metric_name
            order by metric_name
            """,
        )

        snapshots = {
            "scores": scalar(
                connection,
                """
                select count(*) from analytics.player_score_snapshots
                where scope_key=%s and model_version=%s
                """,
                (SCOPE, MODEL),
            ),
            "features": scalar(
                connection,
                """
                select count(*) from analytics.player_feature_snapshots
                where scope_key=%s and model_version=%s
                """,
                (SCOPE, MODEL),
            ),
            "season_players": scalar(
                connection,
                """
                select count(*) from analytics.player_score_snapshots
                where scope_key=%s and model_version=%s and window_key='season'
                """,
                (SCOPE, MODEL),
            ),
            "season_players_450_min": scalar(
                connection,
                """
                select count(*) from analytics.player_score_snapshots
                where scope_key=%s and model_version=%s and window_key='season' and minutes>=450
                """,
                (SCOPE, MODEL),
            ),
            "overall_scores": scalar(
                connection,
                """
                select count(*) from analytics.player_score_snapshots
                where scope_key=%s and model_version=%s and overall_score is not null
                """,
                (SCOPE, MODEL),
            ),
        }

        top_level_states = fetch_dicts(
            connection,
            """
            select evidence_state, count(*) as rows
            from analytics.player_score_snapshots
            where scope_key=%s and model_version=%s
            group by evidence_state order by evidence_state
            """,
            (SCOPE, MODEL),
        )

        dimension_states = fetch_dicts(
            connection,
            """
            select
                e.key as dimension,
                e.value ->> 'evidence_state' as evidence_state,
                count(*) as rows,
                count(*) filter (where e.value ->> 'score' is not null) as scored_rows
            from analytics.player_score_snapshots s
            cross join lateral jsonb_each(s.dimension_evidence) e
            where s.scope_key=%s and s.model_version=%s and s.window_key='season'
              and e.key in ('passing', 'aerial')
            group by e.key, e.value ->> 'evidence_state'
            order by e.key, e.value ->> 'evidence_state'
            """,
            (SCOPE, MODEL),
        )

        season_feature_coverage = fetch_dicts(
            connection,
            """
            select metric_name,
                   count(*) as feature_rows,
                   count(*) filter (where raw_value is not null) as raw_value_rows,
                   count(*) filter (where percentile is not null) as percentile_rows
            from analytics.player_feature_snapshots
            where scope_key=%s and model_version=%s and window_key='season'
              and metric_name in (
                'pass_completion_pct', 'long_passes_accurate',
                'progressive_passes', 'passes_into_final_third',
                'aerial_duels_won', 'aerial_duel_win_pct'
              )
            group by metric_name order by metric_name
            """,
            (SCOPE, MODEL),
        )

        missing_profile_metrics = fetch_dicts(
            connection,
            """
            select missing_metric, count(*) as season_players
            from analytics.player_score_snapshots s
            cross join lateral unnest(s.evidence_metrics_missing) missing_metric
            where s.scope_key=%s and s.model_version=%s and s.window_key='season'
              and missing_metric in (
                'pass_completion_pct', 'long_passes_accurate',
                'progressive_passes', 'passes_into_final_third',
                'aerial_duels_won', 'aerial_duel_win_pct'
              )
            group by missing_metric order by missing_metric
            """,
            (SCOPE, MODEL),
        )

        passing_ready_450 = scalar(
            connection,
            """
            select count(*)
            from analytics.player_score_snapshots s
            where s.scope_key=%s and s.model_version=%s
              and s.window_key='season' and s.minutes>=450
              and s.dimension_evidence -> 'passing' ->> 'evidence_state'='ready'
            """,
            (SCOPE, MODEL),
        )

        ranking_candidates = 0
        try:
            ranking_candidates = scalar(
                connection,
                """
                select count(*) from analytics.product_player_ranking_candidates_v2
                where scope_key=%s and model_version=%s
                """,
                (SCOPE, MODEL),
            )
        except psycopg.Error:
            connection.rollback()

    return {
        "scope": SCOPE,
        "model_version": MODEL,
        "canonical": canonical,
        "player_match_metric_coverage": player_match_metric_coverage,
        "source_metric_counts": source_metric_counts,
        "snapshots": snapshots,
        "top_level_evidence_states": top_level_states,
        "season_dimension_states": dimension_states,
        "season_feature_coverage": season_feature_coverage,
        "season_missing_profile_metrics": missing_profile_metrics,
        "passing_ready_450_min": passing_ready_450,
        "ranking_candidates": ranking_candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.database_url)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
