import { getDatabase } from "@/lib/db/postgres";
import type { DataResult, PlayerRole } from "@/lib/queries/player-analytics";

export interface RatingPlayer {
  playerId: number;
  playerName: string;
  role: PlayerRole;
  performanceScore: number;
  performanceConfidence: number;
  perceptionScore: number | null;
  perceptionConfidence: number;
  perceptionSignal: string;
  ratingGap: number | null;
  ratingConfidence: number;
  ratingSignal: string;
  consensusScore: number | null;
  polarizationScore: number | null;
  evidenceCount: number;
  scoredEvidenceCount: number;
  sourceCount: number;
  scoredSourceCount: number;
}

export interface RatingContext {
  scopeKey: string;
  modelVersion: string;
  performanceModelVersion: string;
  perceptionModelVersion: string;
  calculatedAt: string;
}

export interface RatingFilters {
  role: PlayerRole | "all";
  minConfidence: number;
  search: string;
}

export interface RatingPageData {
  context: RatingContext | null;
  players: RatingPlayer[];
}

interface DbRatingRow {
  player_id: string | number;
  display_name: string;
  role: PlayerRole;
  performance_score: string | number;
  performance_confidence: string | number;
  perception_score: string | number | null;
  perception_confidence: string | number;
  perception_signal: string;
  rating_gap: string | number | null;
  rating_confidence: string | number;
  rating_signal: string;
  consensus_score: string | number | null;
  polarization_score: string | number | null;
  evidence_count: string | number;
  scored_evidence_count: string | number;
  source_count: string | number;
  scored_source_count: string | number;
  scope_key: string;
  model_version: string;
  performance_model_version: string;
  perception_model_version: string;
  calculated_at: Date | string;
}

function numberValue(value: string | number): number {
  return Number(value);
}

function nullableNumber(value: string | number | null): number | null {
  return value === null ? null : Number(value);
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function mapRating(row: DbRatingRow): RatingPlayer {
  return {
    playerId: numberValue(row.player_id),
    playerName: row.display_name,
    role: row.role,
    performanceScore: numberValue(row.performance_score),
    performanceConfidence: numberValue(row.performance_confidence),
    perceptionScore: nullableNumber(row.perception_score),
    perceptionConfidence: numberValue(row.perception_confidence),
    perceptionSignal: row.perception_signal,
    ratingGap: nullableNumber(row.rating_gap),
    ratingConfidence: numberValue(row.rating_confidence),
    ratingSignal: row.rating_signal,
    consensusScore: nullableNumber(row.consensus_score),
    polarizationScore: nullableNumber(row.polarization_score),
    evidenceCount: numberValue(row.evidence_count),
    scoredEvidenceCount: numberValue(row.scored_evidence_count),
    sourceCount: numberValue(row.source_count),
    scoredSourceCount: numberValue(row.scored_source_count),
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message:
      "DATABASE_URL no está configurada. Rating Intelligence leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer Rating Intelligence.",
  };
}

export async function getRatingsPage(
  filters: RatingFilters,
): Promise<DataResult<RatingPageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const contextRows = await sql<DbRatingRow[]>`
      select r.*, p.display_name
      from analytics.player_rating_snapshots as r
      join football.players as p on p.id = r.player_id
      order by r.calculated_at desc
      limit 1
    `;
    const latest = contextRows[0];
    if (!latest) {
      return { status: "ready", data: { context: null, players: [] } };
    }

    const searchPattern = `%${filters.search.trim()}%`;
    const rows = await sql<DbRatingRow[]>`
      select r.*, p.display_name
      from analytics.player_rating_snapshots as r
      join football.players as p on p.id = r.player_id
      where r.scope_key = ${latest.scope_key}
        and r.model_version = ${latest.model_version}
        and (${filters.role} = 'all' or r.role = ${filters.role})
        and r.rating_confidence >= ${filters.minConfidence}
        and (${filters.search.trim()} = '' or p.display_name ilike ${searchPattern})
      order by r.rating_confidence desc, p.display_name
      limit 250
    `;

    return {
      status: "ready",
      data: {
        context: {
          scopeKey: latest.scope_key,
          modelVersion: latest.model_version,
          performanceModelVersion: latest.performance_model_version,
          perceptionModelVersion: latest.perception_model_version,
          calculatedAt: isoValue(latest.calculated_at),
        },
        players: rows.map(mapRating),
      },
    };
  } catch {
    return failed();
  }
}

export async function getPlayerRating(
  playerId: number,
): Promise<DataResult<RatingPlayer | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbRatingRow[]>`
      select r.*, p.display_name
      from analytics.player_rating_snapshots as r
      join football.players as p on p.id = r.player_id
      where r.player_id = ${playerId}
      order by r.calculated_at desc
      limit 1
    `;
    return { status: "ready", data: rows[0] ? mapRating(rows[0]) : null };
  } catch {
    return failed();
  }
}
