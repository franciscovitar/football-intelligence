import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export interface WorldRadarPlayer {
  providerPlayerId: string;
  playerName: string;
  teamName: string | null;
  competitionCode: string;
  competitionName: string;
  country: string;
  position: string | null;
  appearances: number | null;
  minutes: number | null;
  goals: number | null;
  assists: number | null;
  metrics: Record<string, number | null>;
  radarScore: number;
  confidence: number;
  reasons: string[];
  sourceLists: string[];
}

export interface WorldRadarCompetition {
  code: string;
  name: string;
  country: string;
}

export interface WorldRadarContext {
  seasonLabel: string;
  modelVersion: string;
  calculatedAt: string;
  competitions: WorldRadarCompetition[];
}

export interface WorldRadarFilters {
  competitionCode: string;
  position: string;
  minConfidence: number;
  search: string;
}

export interface WorldRadarPageData {
  context: WorldRadarContext | null;
  players: WorldRadarPlayer[];
}

interface DbRadarRow {
  provider_player_id: string;
  player_name: string;
  team_name: string | null;
  competition_code: string;
  competition_name: string;
  country: string;
  position: string | null;
  appearances: number | null;
  minutes: number | null;
  goals: number | null;
  assists: number | null;
  metrics: Record<string, number | null>;
  radar_score: string | number;
  confidence: string | number;
  reasons: string[];
  source_lists: string[];
  season_label: string;
  model_version: string;
  calculated_at: Date | string;
}

function numberValue(value: string | number): number {
  return Number(value);
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function mapRadar(row: DbRadarRow): WorldRadarPlayer {
  return {
    providerPlayerId: row.provider_player_id,
    playerName: row.player_name,
    teamName: row.team_name,
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    country: row.country,
    position: row.position,
    appearances: row.appearances,
    minutes: row.minutes,
    goals: row.goals,
    assists: row.assists,
    metrics: row.metrics ?? {},
    radarScore: numberValue(row.radar_score),
    confidence: numberValue(row.confidence),
    reasons: row.reasons ?? [],
    sourceLists: row.source_lists ?? [],
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. World Radar leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer World Radar.",
  };
}

export async function getWorldRadarPage(
  filters: WorldRadarFilters,
): Promise<DataResult<WorldRadarPageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const latestRows = await sql<{ season_label: string; model_version: string; calculated_at: Date }[]>`
      select season_label, model_version, calculated_at
      from analytics.world_radar_snapshots
      order by calculated_at desc
      limit 1
    `;
    const latest = latestRows[0];
    if (!latest) {
      return { status: "ready", data: { context: null, players: [] } };
    }

    const competitionRows = await sql<WorldRadarCompetition[]>`
      select distinct competition_code as code, competition_name as name, country
      from analytics.world_radar_snapshots
      where season_label = ${latest.season_label}
        and model_version = ${latest.model_version}
      order by name
    `;

    const searchPattern = `%${filters.search.trim()}%`;
    const rows = await sql<DbRadarRow[]>`
      select *
      from analytics.world_radar_snapshots
      where season_label = ${latest.season_label}
        and model_version = ${latest.model_version}
        and (${filters.competitionCode} = '' or competition_code = ${filters.competitionCode})
        and confidence >= ${filters.minConfidence}
        and (${filters.position} = 'all' or position ilike ${filters.position})
        and (
          ${filters.search.trim()} = ''
          or player_name ilike ${searchPattern}
          or coalesce(team_name, '') ilike ${searchPattern}
        )
      order by radar_score desc, confidence desc
      limit 250
    `;

    return {
      status: "ready",
      data: {
        context: {
          seasonLabel: latest.season_label,
          modelVersion: latest.model_version,
          calculatedAt: isoValue(latest.calculated_at),
          competitions: competitionRows,
        },
        players: rows.map(mapRadar),
      },
    };
  } catch {
    return failed();
  }
}
