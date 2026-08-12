import { getDatabase } from "@/lib/db/postgres";

import type { DataResult } from "@/lib/queries/player-analytics";

export type TeamWindow = "season" | "last_10" | "last_5" | "last_3";
export type ResultsProcessSignal =
  | "results_above_process"
  | "results_below_process"
  | "results_aligned";

export interface TeamContext {
  scopeKey: string;
  modelVersion: string;
  calculatedAt: string;
  competitionCode: string;
  competitionName: string;
  seasonLabel: string;
}

export interface RankingTeam {
  teamId: number;
  teamName: string;
  matches: number;
  overallScore: number;
  confidence: number;
  dimensionScores: Record<string, number>;
  resultsProcessDelta: number;
  resultsProcessSignal: ResultsProcessSignal;
  diagnostics: Record<string, unknown>;
  currentElo: number;
  eloChangeLast5: number;
  formScore: number | null;
}

export interface TeamRankingsFilters {
  competitionCode: string;
  window: TeamWindow;
  minConfidence: number;
  search: string;
  limit: number;
}

export interface TeamRankingsData {
  contexts: TeamContext[];
  context: TeamContext | null;
  filters: TeamRankingsFilters;
  teams: RankingTeam[];
}

export interface TeamWindowScore extends Omit<RankingTeam, "formScore"> {
  window: TeamWindow;
  calculatedAt: string;
}

export interface TeamFeature {
  window: TeamWindow;
  metricName: string;
  matches: number;
  observedMatches: number;
  rawValue: number;
  adjustedValue: number;
  percentile: number;
  referenceSampleSize: number;
}

export interface TeamEloPoint {
  matchId: number;
  kickoffAt: string;
  opponentName: string;
  preMatchRating: number;
  expectedResult: number;
  actualResult: number;
  postMatchRating: number;
}

export interface TeamDetail {
  context: TeamContext;
  team: { teamId: number; teamName: string };
  scores: TeamWindowScore[];
  features: TeamFeature[];
  eloHistory: TeamEloPoint[];
}

export interface TeamLabData {
  contexts: Array<TeamContext & { scoreRows: number; teams: number; eloRows: number }>;
  populations: Array<{
    scopeKey: string;
    competitionCode: string;
    seasonLabel: string;
    window: TeamWindow;
    teams: number;
    averageConfidence: number;
    averageScore: number;
  }>;
}

interface DbContextRow {
  scope_key: string;
  model_version: string;
  calculated_at: Date | string;
  competition_code: string;
  competition_name: string;
  season_label: string;
}

interface DbTeamRow {
  team_id: string | number;
  team_name: string;
  matches: string | number;
  overall_score: string | number;
  confidence: string | number;
  dimension_scores: unknown;
  results_process_delta: string | number;
  results_process_signal: ResultsProcessSignal;
  diagnostics: unknown;
  current_elo: string | number;
  elo_change_last_5: string | number;
  form_score: string | number | null;
}

interface DbTeamScoreRow extends DbTeamRow {
  window_key: TeamWindow;
  calculated_at: Date | string;
}

interface DbTeamFeatureRow {
  window_key: TeamWindow;
  metric_name: string;
  matches: string | number;
  observed_matches: string | number;
  raw_value: string | number;
  adjusted_value: string | number;
  percentile: string | number;
  reference_sample_size: string | number;
}

interface DbEloRow {
  match_id: string | number;
  kickoff_at: Date | string;
  opponent_name: string;
  pre_match_rating: string | number;
  expected_result: string | number;
  actual_result: string | number;
  post_match_rating: string | number;
}

interface DbLabContextRow extends DbContextRow {
  score_rows: string | number;
  teams: string | number;
  elo_rows: string | number;
}

interface DbLabPopulationRow {
  scope_key: string;
  competition_code: string;
  season_label: string;
  window_key: TeamWindow;
  teams: string | number;
  average_confidence: string | number;
  average_score: string | number;
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. Team Intelligence necesita PostgreSQL.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer Team Intelligence. Revisá PostgreSQL y el cálculo team-v1.0.",
  };
}

function numberValue(value: string | number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function nullableNumber(value: string | number | null): number | null {
  return value === null ? null : numberValue(value);
}

function isoValue(value: Date | string): string {
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toISOString();
}

function numericObject(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, candidate]) => [key, Number(candidate)] as const)
      .filter((entry) => Number.isFinite(entry[1])),
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function mapContext(row: DbContextRow): TeamContext {
  return {
    scopeKey: row.scope_key,
    modelVersion: row.model_version,
    calculatedAt: isoValue(row.calculated_at),
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    seasonLabel: row.season_label,
  };
}

function mapTeam(row: DbTeamRow): RankingTeam {
  return {
    teamId: numberValue(row.team_id),
    teamName: row.team_name,
    matches: numberValue(row.matches),
    overallScore: numberValue(row.overall_score),
    confidence: numberValue(row.confidence),
    dimensionScores: numericObject(row.dimension_scores),
    resultsProcessDelta: numberValue(row.results_process_delta),
    resultsProcessSignal: row.results_process_signal,
    diagnostics: objectValue(row.diagnostics),
    currentElo: numberValue(row.current_elo),
    eloChangeLast5: numberValue(row.elo_change_last_5),
    formScore: nullableNumber(row.form_score),
  };
}

async function availableContexts(
  sql: NonNullable<ReturnType<typeof getDatabase>>,
): Promise<TeamContext[]> {
  const rows = await sql<DbContextRow[]>`
    select
      ts.scope_key,
      ts.model_version,
      max(ts.calculated_at) as calculated_at,
      c.code as competition_code,
      c.name as competition_name,
      s.label as season_label
    from analytics.team_score_snapshots as ts
    join football.seasons as s on s.id = ts.season_id
    join football.competitions as c on c.id = s.competition_id
    group by ts.scope_key, ts.model_version, c.code, c.name, s.label
    order by max(ts.calculated_at) desc, c.name
  `;
  return rows.map(mapContext);
}

export async function getTeamRankings(
  filters: TeamRankingsFilters,
): Promise<DataResult<TeamRankingsData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const contexts = await availableContexts(sql);
    const context =
      contexts.find((item) => item.competitionCode === filters.competitionCode) ??
      contexts[0] ??
      null;
    if (!context) {
      return { status: "ready", data: { contexts, context: null, filters, teams: [] } };
    }
    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<DbTeamRow[]>`
      select
        t.id as team_id,
        t.name as team_name,
        score.matches,
        score.overall_score,
        score.confidence,
        score.dimension_scores,
        score.results_process_delta,
        score.results_process_signal,
        score.diagnostics,
        score.current_elo,
        score.elo_change_last_5,
        form.overall_score as form_score
      from analytics.team_score_snapshots as score
      join football.teams as t on t.id = score.team_id
      left join analytics.team_score_snapshots as form
        on form.team_id = score.team_id
       and form.scope_key = score.scope_key
       and form.model_version = score.model_version
       and form.window_key = 'last_5'
      where score.scope_key = ${context.scopeKey}
        and score.model_version = ${context.modelVersion}
        and score.window_key = ${filters.window}
        and score.confidence >= ${filters.minConfidence}
        and (${filters.search.trim()} = '' or t.name ilike ${pattern})
      order by score.overall_score desc, score.confidence desc, t.name
      limit ${filters.limit}
    `;
    return { status: "ready", data: { contexts, context, filters, teams: rows.map(mapTeam) } };
  } catch {
    return failed();
  }
}

export async function getTeamDetail(
  teamId: number,
  competitionCode: string,
): Promise<DataResult<TeamDetail | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const contexts = await availableContexts(sql);
    const candidates = competitionCode
      ? contexts.filter((item) => item.competitionCode === competitionCode)
      : contexts;
    let context: TeamContext | null = null;
    for (const candidate of candidates) {
      const rows = await sql<Array<{ exists: boolean }>>`
        select true as exists
        from analytics.team_score_snapshots
        where team_id = ${teamId}
          and scope_key = ${candidate.scopeKey}
          and model_version = ${candidate.modelVersion}
        limit 1
      `;
      if (rows[0]?.exists) {
        context = candidate;
        break;
      }
    }
    if (!context) return { status: "ready", data: null };

    const teamRows = await sql<Array<{ team_id: string | number; team_name: string }>>`
      select id as team_id, name as team_name from football.teams where id = ${teamId}
    `;
    const team = teamRows[0];
    if (!team) return { status: "ready", data: null };

    const [scoreRows, featureRows, eloRows] = await Promise.all([
      sql<DbTeamScoreRow[]>`
        select
          t.id as team_id,
          t.name as team_name,
          score.window_key,
          score.matches,
          score.overall_score,
          score.confidence,
          score.dimension_scores,
          score.results_process_delta,
          score.results_process_signal,
          score.diagnostics,
          score.current_elo,
          score.elo_change_last_5,
          score.overall_score as form_score,
          score.calculated_at
        from analytics.team_score_snapshots as score
        join football.teams as t on t.id = score.team_id
        where score.team_id = ${teamId}
          and score.scope_key = ${context.scopeKey}
          and score.model_version = ${context.modelVersion}
        order by case score.window_key
          when 'season' then 1 when 'last_10' then 2
          when 'last_5' then 3 when 'last_3' then 4 else 5 end
      `,
      sql<DbTeamFeatureRow[]>`
        select
          window_key, metric_name, matches, observed_matches,
          raw_value, adjusted_value, percentile, reference_sample_size
        from analytics.team_feature_snapshots
        where team_id = ${teamId}
          and scope_key = ${context.scopeKey}
          and model_version = ${context.modelVersion}
        order by case window_key
          when 'season' then 1 when 'last_10' then 2
          when 'last_5' then 3 when 'last_3' then 4 else 5 end,
          metric_name
      `,
      sql<DbEloRow[]>`
        select
          elo.match_id,
          m.kickoff_at,
          opponent.name as opponent_name,
          elo.pre_match_rating,
          elo.expected_result,
          elo.actual_result,
          elo.post_match_rating
        from analytics.team_elo_history as elo
        join football.matches as m on m.id = elo.match_id
        join football.teams as opponent on opponent.id = elo.opponent_team_id
        where elo.team_id = ${teamId}
          and elo.season_id = (
            select season_id
            from analytics.team_score_snapshots
            where team_id = ${teamId}
              and scope_key = ${context.scopeKey}
              and model_version = ${context.modelVersion}
            limit 1
          )
          and elo.model_version = ${context.modelVersion}
        order by m.kickoff_at, elo.match_id
      `,
    ]);
    if (scoreRows.length === 0) return { status: "ready", data: null };

    return {
      status: "ready",
      data: {
        context,
        team: { teamId: numberValue(team.team_id), teamName: team.team_name },
        scores: scoreRows.map((row) => ({
          ...mapTeam(row),
          window: row.window_key,
          calculatedAt: isoValue(row.calculated_at),
        })),
        features: featureRows.map((row) => ({
          window: row.window_key,
          metricName: row.metric_name,
          matches: numberValue(row.matches),
          observedMatches: numberValue(row.observed_matches),
          rawValue: numberValue(row.raw_value),
          adjustedValue: numberValue(row.adjusted_value),
          percentile: numberValue(row.percentile),
          referenceSampleSize: numberValue(row.reference_sample_size),
        })),
        eloHistory: eloRows.map((row) => ({
          matchId: numberValue(row.match_id),
          kickoffAt: isoValue(row.kickoff_at),
          opponentName: row.opponent_name,
          preMatchRating: numberValue(row.pre_match_rating),
          expectedResult: numberValue(row.expected_result),
          actualResult: numberValue(row.actual_result),
          postMatchRating: numberValue(row.post_match_rating),
        })),
      },
    };
  } catch {
    return failed();
  }
}

export async function getTeamLabData(): Promise<DataResult<TeamLabData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const [contexts, populations] = await Promise.all([
      sql<DbLabContextRow[]>`
        select
          score.scope_key,
          score.model_version,
          max(score.calculated_at) as calculated_at,
          c.code as competition_code,
          c.name as competition_name,
          s.label as season_label,
          count(*) as score_rows,
          count(distinct score.team_id) as teams,
          (
            select count(*) from analytics.team_elo_history as elo
            where elo.season_id = score.season_id
              and elo.model_version = score.model_version
          ) as elo_rows
        from analytics.team_score_snapshots as score
        join football.seasons as s on s.id = score.season_id
        join football.competitions as c on c.id = s.competition_id
        group by score.scope_key, score.model_version, score.season_id, c.code, c.name, s.label
        order by max(score.calculated_at) desc, c.code
      `,
      sql<DbLabPopulationRow[]>`
        select
          score.scope_key,
          c.code as competition_code,
          s.label as season_label,
          score.window_key,
          count(*) as teams,
          avg(score.confidence) as average_confidence,
          avg(score.overall_score) as average_score
        from analytics.team_score_snapshots as score
        join football.seasons as s on s.id = score.season_id
        join football.competitions as c on c.id = s.competition_id
        group by score.scope_key, c.code, s.label, score.window_key
        order by c.code, s.label, score.window_key
      `,
    ]);
    return {
      status: "ready",
      data: {
        contexts: contexts.map((row) => ({
          ...mapContext(row),
          scoreRows: numberValue(row.score_rows),
          teams: numberValue(row.teams),
          eloRows: numberValue(row.elo_rows),
        })),
        populations: populations.map((row) => ({
          scopeKey: row.scope_key,
          competitionCode: row.competition_code,
          seasonLabel: row.season_label,
          window: row.window_key,
          teams: numberValue(row.teams),
          averageConfidence: numberValue(row.average_confidence),
          averageScore: numberValue(row.average_score),
        })),
      },
    };
  } catch {
    return failed();
  }
}
