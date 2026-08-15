import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

/**
 * All stat fields are nullable by design: a NULL here means "not observed
 * by this source," never a real zero. Callers must render an explicit
 * "no disponible" state for a null field, never 0 or a blank cell.
 */
export interface PlayerSeasonStats {
  seasonLabel: string;
  minutes: number | null;
  starts: number | null;
  appearances: number | null;
  goals: number | null;
  assists: number | null;
  cleanSheets: number | null;
  goalsConceded: number | null;
  ownGoals: number | null;
  penaltiesSaved: number | null;
  penaltiesMissed: number | null;
  yellowCards: number | null;
  redCards: number | null;
  saves: number | null;
  bonus: number | null;
  bps: number | null;
  influence: number | null;
  creativity: number | null;
  threat: number | null;
  ictIndex: number | null;
  tackles: number | null;
  recoveries: number | null;
  clearancesBlocksInterceptions: number | null;
  defensiveContribution: number | null;
  expectedGoals: number | null;
  expectedAssists: number | null;
  expectedGoalInvolvements: number | null;
  expectedGoalsConceded: number | null;
  source: string;
  sourceUrl: string;
  retrievedAt: string;
  semanticVersion: string;
}

interface DbSeasonStatsRow {
  season_label: string;
  minutes: string | number | null;
  starts: string | number | null;
  appearances: string | number | null;
  goals: string | number | null;
  assists: string | number | null;
  clean_sheets: string | number | null;
  goals_conceded: string | number | null;
  own_goals: string | number | null;
  penalties_saved: string | number | null;
  penalties_missed: string | number | null;
  yellow_cards: string | number | null;
  red_cards: string | number | null;
  saves: string | number | null;
  bonus: string | number | null;
  bps: string | number | null;
  influence: string | number | null;
  creativity: string | number | null;
  threat: string | number | null;
  ict_index: string | number | null;
  tackles: string | number | null;
  recoveries: string | number | null;
  clearances_blocks_interceptions: string | number | null;
  defensive_contribution: string | number | null;
  expected_goals: string | number | null;
  expected_assists: string | number | null;
  expected_goal_involvements: string | number | null;
  expected_goals_conceded: string | number | null;
  source: string;
  source_url: string;
  retrieved_at: Date | string;
  semantic_version: string;
}

function nullableNumber(value: string | number | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function mapSeasonStats(row: DbSeasonStatsRow): PlayerSeasonStats {
  return {
    seasonLabel: row.season_label,
    minutes: nullableNumber(row.minutes),
    starts: nullableNumber(row.starts),
    appearances: nullableNumber(row.appearances),
    goals: nullableNumber(row.goals),
    assists: nullableNumber(row.assists),
    cleanSheets: nullableNumber(row.clean_sheets),
    goalsConceded: nullableNumber(row.goals_conceded),
    ownGoals: nullableNumber(row.own_goals),
    penaltiesSaved: nullableNumber(row.penalties_saved),
    penaltiesMissed: nullableNumber(row.penalties_missed),
    yellowCards: nullableNumber(row.yellow_cards),
    redCards: nullableNumber(row.red_cards),
    saves: nullableNumber(row.saves),
    bonus: nullableNumber(row.bonus),
    bps: nullableNumber(row.bps),
    influence: nullableNumber(row.influence),
    creativity: nullableNumber(row.creativity),
    threat: nullableNumber(row.threat),
    ictIndex: nullableNumber(row.ict_index),
    tackles: nullableNumber(row.tackles),
    recoveries: nullableNumber(row.recoveries),
    clearancesBlocksInterceptions: nullableNumber(row.clearances_blocks_interceptions),
    defensiveContribution: nullableNumber(row.defensive_contribution),
    expectedGoals: nullableNumber(row.expected_goals),
    expectedAssists: nullableNumber(row.expected_assists),
    expectedGoalInvolvements: nullableNumber(row.expected_goal_involvements),
    expectedGoalsConceded: nullableNumber(row.expected_goals_conceded),
    source: row.source,
    sourceUrl: row.source_url,
    retrievedAt: isoValue(row.retrieved_at),
    semanticVersion: row.semantic_version,
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. Los datos reales de temporada se leerán cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudieron leer los datos reales de temporada.",
  };
}

/**
 * A player can have season-aggregate rows from more than one source (unique
 * per player+season+source, never averaged across sources). This returns
 * the most recently retrieved row as the single displayed snapshot -- its
 * provenance line always names the exact source, never implying consensus.
 */
export async function getPlayerSeasonStats(
  playerId: number,
): Promise<DataResult<PlayerSeasonStats | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbSeasonStatsRow[]>`
      select
        pss.*,
        s.label as season_label
      from football.player_season_stats as pss
      join football.seasons as s on s.id = pss.season_id
      where pss.player_id = ${playerId}
      order by pss.retrieved_at desc
      limit 1
    `;
    return { status: "ready", data: rows[0] ? mapSeasonStats(rows[0]) : null };
  } catch {
    return failed();
  }
}
