import { getDatabase } from "@/lib/db/postgres";
import type { DataResult, PlayerRole } from "@/lib/queries/player-analytics";

export interface MetaPlayer {
  playerId: number;
  playerName: string;
  role: PlayerRole;
  performanceScore: number;
  performanceConfidence: number;
  formScore: number | null;
  formConfidence: number | null;
  stableScore: number;
  stableConfidence: number;
  expectationScore: number | null;
  expectationConfidence: number | null;
  surpriseDelta: number | null;
  surpriseSignal: string;
  trendDelta: number | null;
  trendConfidence: number | null;
  trendSignal: string;
  watchlistScore: number;
  watchlistSignal: string;
  historySeasons: number;
}

export interface MetaContext {
  scopeKey: string;
  modelVersion: string;
  sourceModelVersion: string;
  calculatedAt: string;
}

export interface MetaFilters {
  role: PlayerRole | "all";
  minConfidence: number;
  search: string;
}

export interface MetaPageData {
  context: MetaContext | null;
  players: MetaPlayer[];
}

interface DbMetaRow {
  player_id: string | number;
  display_name: string;
  role: PlayerRole;
  performance_score: string | number;
  performance_confidence: string | number;
  form_score: string | number | null;
  form_confidence: string | number | null;
  stable_score: string | number;
  stable_confidence: string | number;
  expectation_score: string | number | null;
  expectation_confidence: string | number | null;
  surprise_delta: string | number | null;
  surprise_signal: string;
  trend_delta: string | number | null;
  trend_confidence: string | number | null;
  trend_signal: string;
  watchlist_score: string | number;
  watchlist_signal: string;
  history_seasons: string | number;
  scope_key: string;
  model_version: string;
  source_model_version: string;
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

function mapMeta(row: DbMetaRow): MetaPlayer {
  return {
    playerId: numberValue(row.player_id),
    playerName: row.display_name,
    role: row.role,
    performanceScore: numberValue(row.performance_score),
    performanceConfidence: numberValue(row.performance_confidence),
    formScore: nullableNumber(row.form_score),
    formConfidence: nullableNumber(row.form_confidence),
    stableScore: numberValue(row.stable_score),
    stableConfidence: numberValue(row.stable_confidence),
    expectationScore: nullableNumber(row.expectation_score),
    expectationConfidence: nullableNumber(row.expectation_confidence),
    surpriseDelta: nullableNumber(row.surprise_delta),
    surpriseSignal: row.surprise_signal,
    trendDelta: nullableNumber(row.trend_delta),
    trendConfidence: nullableNumber(row.trend_confidence),
    trendSignal: row.trend_signal,
    watchlistScore: numberValue(row.watchlist_score),
    watchlistSignal: row.watchlist_signal,
    historySeasons: numberValue(row.history_seasons),
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message:
      "DATABASE_URL no está configurada. Meta Intelligence leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer Expectation & Meta Intelligence.",
  };
}

export async function getMetaPage(
  filters: MetaFilters,
): Promise<DataResult<MetaPageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const contextRows = await sql<DbMetaRow[]>`
      select
        m.*, p.display_name
      from analytics.player_meta_snapshots as m
      join football.players as p on p.id = m.player_id
      order by m.calculated_at desc
      limit 1
    `;
    const latest = contextRows[0];
    if (!latest) {
      return { status: "ready", data: { context: null, players: [] } };
    }

    const searchPattern = `%${filters.search.trim()}%`;
    const rows = await sql<DbMetaRow[]>`
      select
        m.*, p.display_name
      from analytics.player_meta_snapshots as m
      join football.players as p on p.id = m.player_id
      where m.scope_key = ${latest.scope_key}
        and m.model_version = ${latest.model_version}
        and (${filters.role} = 'all' or m.role = ${filters.role})
        and m.stable_confidence >= ${filters.minConfidence}
        and (${filters.search.trim()} = '' or p.display_name ilike ${searchPattern})
      order by m.watchlist_score desc, m.stable_score desc, p.display_name
      limit 250
    `;

    return {
      status: "ready",
      data: {
        context: {
          scopeKey: latest.scope_key,
          modelVersion: latest.model_version,
          sourceModelVersion: latest.source_model_version,
          calculatedAt: isoValue(latest.calculated_at),
        },
        players: rows.map(mapMeta),
      },
    };
  } catch {
    return failed();
  }
}

export async function getPlayerMeta(
  playerId: number,
): Promise<DataResult<MetaPlayer | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbMetaRow[]>`
      select
        m.*, p.display_name
      from analytics.player_meta_snapshots as m
      join football.players as p on p.id = m.player_id
      where m.player_id = ${playerId}
      order by m.calculated_at desc
      limit 1
    `;
    return { status: "ready", data: rows[0] ? mapMeta(rows[0]) : null };
  } catch {
    return failed();
  }
}
