import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export interface TacticalAlternativeFormation {
  formation: string;
  matches: number;
  share: number;
}

export interface TacticalTeam {
  teamId: number;
  teamName: string;
  matches: number;
  sourceConfidence: number;
  controlScore: number | null;
  attackingVolumeScore: number | null;
  defensiveResistanceScore: number | null;
  styleSignal: string;
  defensiveSignal: string;
  primaryFormation: string | null;
  formationMatches: number;
  formationShare: number | null;
  formationConfidence: number;
  formationSignal: string;
  alternativeFormations: TacticalAlternativeFormation[];
  tacticalConfidence: number;
  summary: string;
}

export interface TacticalContext {
  scopeKey: string;
  modelVersion: string;
  sourceModelVersion: string;
  calculatedAt: string;
  competitionCode: string;
  competitionName: string;
  seasonLabel: string;
}

export interface TacticalFilters {
  competitionCode: string;
  minConfidence: number;
  search: string;
}

export interface TacticalPageData {
  contexts: TacticalContext[];
  context: TacticalContext | null;
  filters: TacticalFilters;
  teams: TacticalTeam[];
}

interface DbTacticalRow {
  team_id: string | number;
  team_name: string;
  matches: string | number;
  source_confidence: string | number;
  control_score: string | number | null;
  attacking_volume_score: string | number | null;
  defensive_resistance_score: string | number | null;
  style_signal: string;
  defensive_signal: string;
  primary_formation: string | null;
  formation_matches: string | number;
  formation_share: string | number | null;
  formation_confidence: string | number;
  formation_signal: string;
  alternative_formations: unknown;
  tactical_confidence: string | number;
  summary: string;
  scope_key: string;
  model_version: string;
  source_model_version: string;
  calculated_at: Date | string;
  competition_code: string;
  competition_name: string;
  season_label: string;
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

function alternatives(value: unknown): TacticalAlternativeFormation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const row = item as Record<string, unknown>;
    if (typeof row.formation !== "string") return [];
    const matches = Number(row.matches);
    const share = Number(row.share);
    if (!Number.isFinite(matches) || !Number.isFinite(share)) return [];
    return [{ formation: row.formation, matches, share }];
  });
}

function mapTeam(row: DbTacticalRow): TacticalTeam {
  return {
    teamId: numberValue(row.team_id),
    teamName: row.team_name,
    matches: numberValue(row.matches),
    sourceConfidence: numberValue(row.source_confidence),
    controlScore: nullableNumber(row.control_score),
    attackingVolumeScore: nullableNumber(row.attacking_volume_score),
    defensiveResistanceScore: nullableNumber(row.defensive_resistance_score),
    styleSignal: row.style_signal,
    defensiveSignal: row.defensive_signal,
    primaryFormation: row.primary_formation,
    formationMatches: numberValue(row.formation_matches),
    formationShare: nullableNumber(row.formation_share),
    formationConfidence: numberValue(row.formation_confidence),
    formationSignal: row.formation_signal,
    alternativeFormations: alternatives(row.alternative_formations),
    tacticalConfidence: numberValue(row.tactical_confidence),
    summary: row.summary,
  };
}

function mapContext(row: DbTacticalRow): TacticalContext {
  return {
    scopeKey: row.scope_key,
    modelVersion: row.model_version,
    sourceModelVersion: row.source_model_version,
    calculatedAt: isoValue(row.calculated_at),
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    seasonLabel: row.season_label,
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message:
      "DATABASE_URL no está configurada. Tactical Intelligence necesita PostgreSQL.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer Tactical Intelligence.",
  };
}

async function availableContexts(
  sql: NonNullable<ReturnType<typeof getDatabase>>,
): Promise<TacticalContext[]> {
  const rows = await sql<DbTacticalRow[]>`
    select
      tactical.*,
      t.name as team_name,
      c.code as competition_code,
      c.name as competition_name,
      s.label as season_label
    from analytics.team_tactical_snapshots as tactical
    join football.teams as t on t.id = tactical.team_id
    join football.seasons as s on s.id = tactical.season_id
    join football.competitions as c on c.id = s.competition_id
    order by tactical.calculated_at desc
  `;

  const seen = new Set<string>();
  const contexts: TacticalContext[] = [];
  for (const row of rows) {
    const key = `${row.scope_key}:${row.model_version}`;
    if (seen.has(key)) continue;
    seen.add(key);
    contexts.push(mapContext(row));
  }
  return contexts;
}

export async function getTacticalPage(
  filters: TacticalFilters,
): Promise<DataResult<TacticalPageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const contexts = await availableContexts(sql);
    const context =
      contexts.find((item) => item.competitionCode === filters.competitionCode) ??
      contexts[0] ??
      null;

    if (!context) {
      return {
        status: "ready",
        data: { contexts, context: null, filters, teams: [] },
      };
    }

    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<DbTacticalRow[]>`
      select
        tactical.*,
        t.name as team_name,
        c.code as competition_code,
        c.name as competition_name,
        s.label as season_label
      from analytics.team_tactical_snapshots as tactical
      join football.teams as t on t.id = tactical.team_id
      join football.seasons as s on s.id = tactical.season_id
      join football.competitions as c on c.id = s.competition_id
      where tactical.scope_key = ${context.scopeKey}
        and tactical.model_version = ${context.modelVersion}
        and tactical.tactical_confidence >= ${filters.minConfidence}
        and (${filters.search.trim()} = '' or t.name ilike ${pattern})
      order by tactical.tactical_confidence desc, t.name
      limit 100
    `;

    return {
      status: "ready",
      data: {
        contexts,
        context,
        filters,
        teams: rows.map(mapTeam),
      },
    };
  } catch {
    return failed();
  }
}

export async function getTeamTactical(
  teamId: number,
  competitionCode: string,
): Promise<DataResult<TacticalTeam | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbTacticalRow[]>`
      select
        tactical.*,
        t.name as team_name,
        c.code as competition_code,
        c.name as competition_name,
        s.label as season_label
      from analytics.team_tactical_snapshots as tactical
      join football.teams as t on t.id = tactical.team_id
      join football.seasons as s on s.id = tactical.season_id
      join football.competitions as c on c.id = s.competition_id
      where tactical.team_id = ${teamId}
        and (${competitionCode} = '' or c.code = ${competitionCode})
      order by tactical.calculated_at desc
      limit 1
    `;
    return { status: "ready", data: rows[0] ? mapTeam(rows[0]) : null };
  } catch {
    return failed();
  }
}
