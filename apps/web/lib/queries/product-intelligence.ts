import { getDatabase } from "@/lib/db/postgres";
import type { PositionFamily } from "@/lib/position-family";
import type {
  AnalyticsWindow,
  DataResult,
  PlayerRole,
  ScoreEvidenceState,
} from "@/lib/queries/player-analytics";

export const PLAYER_RANKING_DIMENSIONS = [
  "overall",
  "performance",
  "underlying_performance",
  "finishing",
  "shot_generation",
  "creation",
  "progression",
  "passing",
  "one_v_one",
  "defence",
  "ball_winning",
  "aerial",
  "goalkeeping",
] as const;

export const TEAM_RANKING_DIMENSIONS = [
  "overall",
  "attack",
  "defence",
  "creation",
  "finishing",
  "chance_quality",
  "shot_generation",
  "control",
  "progression",
  "penetration",
  "build_up",
  "pressing",
  "offensive_transition",
  "defensive_transition",
  "set_pieces",
] as const;

export type PlayerRankingDimension = (typeof PLAYER_RANKING_DIMENSIONS)[number];
export type TeamRankingDimension = (typeof TEAM_RANKING_DIMENSIONS)[number];
export type TeamWindow = AnalyticsWindow;

export interface ProductContext {
  scopeKey: string;
  modelVersion: string;
  calculatedAt: string;
  competitionCode: string | null;
  competitionName: string | null;
  seasonLabel: string | null;
}

export interface ProductDimensionEvidence {
  score: number | null;
  evidenceCoveragePct: number;
  evidenceState: ScoreEvidenceState;
  availableMetrics: string[];
  missingMetrics: string[];
  coreMetrics: string[];
}

export interface ProductPlayerRanking {
  playerId: number;
  playerName: string;
  teamName: string | null;
  competitionCode: string | null;
  competitionName: string | null;
  seasonLabel: string | null;
  role: PlayerRole;
  positionFamily: PositionFamily | null;
  minutes: number;
  appearances: number;
  score: number;
  confidence: number;
  evidenceCoveragePct: number;
  dimension: PlayerRankingDimension;
  keyEvidence: string[];
}

export interface ProductMetric {
  metricName: string;
  metricUnit: string;
  metricKind: string;
  metricGranularity: string;
  rawValue: number | null;
  per90Value: number | null;
  adjustedValue: number | null;
  percentile: number | null;
  percentileState: string;
  comparisonGroup: string | null;
  referenceSampleSize: number;
}

export interface ProductPlayerWindow {
  window: AnalyticsWindow;
  role: PlayerRole;
  positionFamily: PositionFamily | null;
  minutes: number;
  appearances: number;
  overallScore: number | null;
  confidence: number;
  evidenceCoveragePct: number;
  evidenceState: ScoreEvidenceState;
  dimensions: Record<string, ProductDimensionEvidence>;
  calculatedAt: string;
}

export interface ProductPlayerDetail {
  context: ProductContext;
  player: {
    playerId: number;
    playerName: string;
    teamName: string | null;
    competitionCode: string | null;
    competitionName: string | null;
    seasonLabel: string | null;
    nationalityCode: string | null;
    dateOfBirth: string | null;
  };
  windows: ProductPlayerWindow[];
  metrics: Record<AnalyticsWindow, ProductMetric[]>;
}

export interface ProductTeamRanking {
  teamId: number;
  teamName: string;
  competitionCode: string;
  competitionName: string;
  seasonLabel: string;
  matches: number;
  score: number;
  confidence: number;
  evidenceCoveragePct: number;
  dimension: TeamRankingDimension;
  keyEvidence: string[];
}

export interface ProductTeamWindow {
  window: TeamWindow;
  matches: number;
  overallScore: number | null;
  confidence: number;
  evidenceCoveragePct: number;
  evidenceState: ScoreEvidenceState;
  dimensions: Record<string, ProductDimensionEvidence>;
  diagnostics: string[];
  calculatedAt: string;
}

export interface ProductTeamDetail {
  context: ProductContext;
  team: { teamId: number; teamName: string };
  windows: ProductTeamWindow[];
  metrics: Record<TeamWindow, ProductMetric[]>;
}

export interface PlayerRankingFilters {
  competitionCode: string;
  seasonLabel: string;
  window: AnalyticsWindow;
  positionFamily: PositionFamily | "all";
  minMinutes: number;
  minConfidence: number;
  search: string;
  dimension: PlayerRankingDimension;
  limit: number;
}

export interface TeamRankingFilters {
  competitionCode: string;
  seasonLabel: string;
  window: TeamWindow;
  minConfidence: number;
  search: string;
  dimension: TeamRankingDimension;
  limit: number;
}

export interface ProductDiagnostic {
  diagnosticCode: string;
  entityType: "player" | "team";
  entityId: number;
  entityName: string;
  severity: string;
  confidence: number;
  supportingMetrics: Record<string, unknown>;
  window: string;
  modelVersion: string;
}

export interface ProductHomeData {
  context: ProductContext | null;
  bestPlayers: ProductPlayerRanking[];
  bestTeams: ProductTeamRanking[];
  formPlayers: ProductPlayerRanking[];
  nowSignals: ProductDiagnostic[];
  surprises: ProductDiagnostic[];
  disappointments: ProductDiagnostic[];
  underrated: ProductPlayerRanking[];
  overrated: ProductPlayerRanking[];
  watchlist: WatchlistPlayer[];
  teamSignals: ProductDiagnostic[];
}

export interface CompareOption {
  id: number;
  name: string;
  subtitle: string;
}

export interface WatchlistPlayer {
  playerId: number;
  playerName: string;
  teamName: string | null;
  category: string;
  reason: string | null;
  createdAt: string;
  score: number | null;
  confidence: number;
  evidenceState: ScoreEvidenceState;
}

export interface WatchlistData {
  entries: WatchlistPlayer[];
  candidates: CompareOption[];
  automaticSuggestions: ProductDiagnostic[];
}

type Sql = NonNullable<ReturnType<typeof getDatabase>>;

interface ContextRow {
  scope_key: string;
  model_version: string;
  calculated_at: Date | string;
  competition_code: string | null;
  competition_name: string | null;
  season_label: string | null;
}

interface RankingRow {
  entity_id: string | number;
  entity_name: string;
  team_name: string | null;
  competition_code: string | null;
  competition_name: string | null;
  season_label: string | null;
  role: PlayerRole | null;
  position_family: PositionFamily | null;
  minutes: string | number | null;
  appearances: string | number | null;
  matches: string | number | null;
  ranking_score: string | number | null;
  confidence: string | number;
  evidence_coverage_pct: string | number;
  dimension_evidence: unknown;
}

interface ScoreRow {
  window_key: AnalyticsWindow;
  role: PlayerRole;
  position_family: PositionFamily | null;
  minutes: string | number;
  appearances: string | number;
  matches?: string | number;
  overall_score: string | number | null;
  confidence: string | number;
  evidence_coverage_pct: string | number;
  evidence_state: ScoreEvidenceState;
  dimension_evidence: unknown;
  diagnostics?: unknown;
  calculated_at: Date | string;
}

interface MetricRow {
  window_key: AnalyticsWindow;
  metric_name: string;
  metric_unit: string;
  metric_kind: string;
  metric_granularity?: string;
  raw_value: string | number | null;
  per90_value?: string | number | null;
  adjusted_value: string | number | null;
  percentile: string | number | null;
  percentile_state?: string;
  comparison_group: string | null;
  reference_sample_size: string | number;
}

interface DiagnosticRow {
  diagnostic_code: string;
  entity_type: "player" | "team";
  entity_id: string | number;
  entity_name: string;
  severity: string;
  confidence: string | number;
  supporting_metrics: unknown;
  window_key: string;
  model_version: string;
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "La experiencia necesita una conexión PostgreSQL para leer evidencia real V2.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No pudimos leer la inteligencia V2. Revisá el estado del snapshot real.",
  };
}

function numberValue(value: string | number | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function nullableNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isoValue(value: Date | string): string {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toISOString();
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function dimensions(value: unknown): Record<string, ProductDimensionEvidence> {
  const source = objectValue(value);
  const result: Record<string, ProductDimensionEvidence> = {};
  for (const [name, raw] of Object.entries(source)) {
    const item = objectValue(raw);
    const state = item.evidence_state;
    if (state !== "ready" && state !== "partial" && state !== "insufficient_data") continue;
    result[name] = {
      score: nullableNumber(item.score as string | number | null),
      evidenceCoveragePct: numberValue(item.evidence_coverage_pct as string | number),
      evidenceState: state,
      availableMetrics: stringList(item.evidence_metrics_available),
      missingMetrics: stringList(item.evidence_metrics_missing),
      coreMetrics: stringList(item.evidence_core_metrics),
    };
  }
  return result;
}

function diagnostics(value: unknown): string[] {
  return stringList(objectValue(value).signals);
}

function context(row: ContextRow): ProductContext {
  return {
    scopeKey: row.scope_key,
    modelVersion: row.model_version,
    calculatedAt: isoValue(row.calculated_at),
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    seasonLabel: row.season_label,
  };
}

async function latestPlayerContext(sql: Sql): Promise<ProductContext | null> {
  const rows = await sql<ContextRow[]>`
    select
      detail.scope_key,
      detail.model_version,
      max(detail.calculated_at) as calculated_at,
      null::text as competition_code,
      null::text as competition_name,
      null::text as season_label
    from analytics.product_player_detail_v2 as detail
    group by detail.scope_key, detail.model_version
    order by max(detail.calculated_at) desc
    limit 1
  `;
  return rows[0] ? context(rows[0]) : null;
}

function mapPlayerRanking(
  row: RankingRow,
  dimension: PlayerRankingDimension,
): ProductPlayerRanking {
  const evidence = dimensions(row.dimension_evidence)[dimension];
  return {
    playerId: numberValue(row.entity_id),
    playerName: row.entity_name,
    teamName: row.team_name,
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    seasonLabel: row.season_label,
    role: row.role ?? "midfielder",
    positionFamily: row.position_family,
    minutes: numberValue(row.minutes),
    appearances: numberValue(row.appearances),
    score: numberValue(row.ranking_score),
    confidence: numberValue(row.confidence),
    evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
    dimension,
    keyEvidence: evidence?.availableMetrics.slice(0, 3) ?? [],
  };
}

export async function getProductPlayerRankings(
  filters: PlayerRankingFilters,
): Promise<DataResult<{ context: ProductContext | null; players: ProductPlayerRanking[] }>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const activeContext = await latestPlayerContext(sql);
    if (!activeContext) return { status: "ready", data: { context: null, players: [] } };
    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<RankingRow[]>`
      select
        score.player_id as entity_id,
        player.display_name as entity_name,
        latest.team_name,
        latest.competition_code,
        latest.competition_name,
        latest.season_label,
        score.role,
        score.position_family,
        score.minutes,
        score.appearances,
        null::integer as matches,
        case
          when ${filters.dimension} = 'overall' then score.overall_score
          else nullif(score.dimension_evidence -> ${filters.dimension} ->> 'score', '')::numeric
        end as ranking_score,
        score.confidence,
        score.evidence_coverage_pct,
        score.dimension_evidence
      from analytics.product_player_ranking_candidates_v2 as score
      join football.players as player on player.id = score.player_id
      left join lateral (
        select
          team.name as team_name,
          competition.code as competition_code,
          competition.name as competition_name,
          season.label as season_label
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        join football.seasons as season on season.id = match.season_id
        join football.competitions as competition on competition.id = season.competition_id
        join football.teams as team on team.id = appearance.team_id
        where appearance.player_id = score.player_id
        order by match.kickoff_at desc nulls last, match.id desc
        limit 1
      ) as latest on true
      where score.scope_key = ${activeContext.scopeKey}
        and score.model_version = ${activeContext.modelVersion}
        and score.window_key = ${filters.window}
        and score.minutes >= ${filters.minMinutes}
        and score.confidence >= ${Math.max(0.4, filters.minConfidence)}
        and (${filters.positionFamily} = 'all' or score.position_family = ${filters.positionFamily})
        and (${filters.competitionCode} = '' or latest.competition_code = ${filters.competitionCode})
        and (${filters.seasonLabel} = '' or latest.season_label = ${filters.seasonLabel})
        and (${filters.search.trim()} = '' or player.display_name ilike ${pattern})
        and (
          (${filters.dimension} = 'overall'
            and score.evidence_state = 'ready'
            and score.overall_score is not null)
          or
          (${filters.dimension} <> 'overall'
            and score.dimension_evidence -> ${filters.dimension} ->> 'evidence_state' = 'ready'
            and score.dimension_evidence -> ${filters.dimension} ->> 'score' is not null)
        )
      order by ranking_score desc, score.confidence desc, player.display_name
      limit ${filters.limit}
    `;
    return {
      status: "ready",
      data: { context: activeContext, players: rows.map((row) => mapPlayerRanking(row, filters.dimension)) },
    };
  } catch {
    return failed();
  }
}

export async function getProductPlayerDetail(
  playerId: number,
): Promise<DataResult<ProductPlayerDetail | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const contextRows = await sql<ContextRow[]>`
      select
        detail.scope_key,
        detail.model_version,
        max(detail.calculated_at) as calculated_at,
        latest.competition_code,
        latest.competition_name,
        latest.season_label
      from analytics.product_player_detail_v2 as detail
      left join lateral (
        select competition.code as competition_code, competition.name as competition_name,
               season.label as season_label
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        join football.seasons as season on season.id = match.season_id
        join football.competitions as competition on competition.id = season.competition_id
        where appearance.player_id = detail.player_id
        order by match.kickoff_at desc nulls last, match.id desc
        limit 1
      ) as latest on true
      where detail.player_id = ${playerId}
      group by detail.scope_key, detail.model_version,
               latest.competition_code, latest.competition_name, latest.season_label
      order by max(detail.calculated_at) desc
      limit 1
    `;
    const active = contextRows[0];
    if (!active) return { status: "ready", data: null };

    const [playerRows, scoreRows, metricRows] = await Promise.all([
      sql<Array<{
        player_id: string | number;
        display_name: string;
        nationality_code: string | null;
        date_of_birth: Date | string | null;
        team_name: string | null;
      }>>`
        select player.id as player_id, player.display_name, player.nationality_code,
               player.date_of_birth, latest.team_name
        from football.players as player
        left join lateral (
          select team.name as team_name
          from football.player_appearances as appearance
          join football.matches as match on match.id = appearance.match_id
          join football.teams as team on team.id = appearance.team_id
          where appearance.player_id = player.id
          order by match.kickoff_at desc nulls last, match.id desc
          limit 1
        ) as latest on true
        where player.id = ${playerId}
      `,
      sql<ScoreRow[]>`
        select window_key, role, position_family, minutes, appearances, overall_score,
               confidence, evidence_coverage_pct, evidence_state, dimension_evidence,
               calculated_at
        from analytics.product_player_detail_v2
        where player_id = ${playerId}
          and scope_key = ${active.scope_key}
          and model_version = ${active.model_version}
        order by case window_key
          when 'season' then 1 when 'last_10' then 2 when 'last_5' then 3 else 4 end
      `,
      sql<MetricRow[]>`
        select window_key, metric_name, metric_unit, metric_kind, metric_granularity,
               raw_value, per90_value, adjusted_per90 as adjusted_value, percentile,
               percentile_state, comparison_group, reference_sample_size
        from analytics.player_feature_snapshots
        where player_id = ${playerId}
          and scope_key = ${active.scope_key}
          and model_version = ${active.model_version}
          and data_context = 'real'
        order by window_key, metric_name
      `,
    ]);
    const player = playerRows[0];
    if (!player) return { status: "ready", data: null };
    const grouped = { season: [], last_10: [], last_5: [], last_3: [] } as Record<
      AnalyticsWindow,
      ProductMetric[]
    >;
    for (const row of metricRows) {
      grouped[row.window_key].push({
        metricName: row.metric_name,
        metricUnit: row.metric_unit,
        metricKind: row.metric_kind,
        metricGranularity: row.metric_granularity ?? "player_match",
        rawValue: nullableNumber(row.raw_value),
        per90Value: nullableNumber(row.per90_value),
        adjustedValue: nullableNumber(row.adjusted_value),
        percentile: nullableNumber(row.percentile),
        percentileState: row.percentile_state ?? "not_applicable",
        comparisonGroup: row.comparison_group,
        referenceSampleSize: numberValue(row.reference_sample_size),
      });
    }
    return {
      status: "ready",
      data: {
        context: context(active),
        player: {
          playerId: numberValue(player.player_id),
          playerName: player.display_name,
          teamName: player.team_name,
          competitionCode: active.competition_code,
          competitionName: active.competition_name,
          seasonLabel: active.season_label,
          nationalityCode: player.nationality_code,
          dateOfBirth:
            player.date_of_birth === null ? null : isoValue(player.date_of_birth).slice(0, 10),
        },
        windows: scoreRows.map((row) => ({
          window: row.window_key,
          role: row.role,
          positionFamily: row.position_family,
          minutes: numberValue(row.minutes),
          appearances: numberValue(row.appearances),
          overallScore: nullableNumber(row.overall_score),
          confidence: numberValue(row.confidence),
          evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
          evidenceState: row.evidence_state,
          dimensions: dimensions(row.dimension_evidence),
          calculatedAt: isoValue(row.calculated_at),
        })),
        metrics: grouped,
      },
    };
  } catch {
    return failed();
  }
}

async function latestTeamContext(
  sql: Sql,
  competitionCode = "",
  seasonLabel = "",
): Promise<ProductContext | null> {
  const rows = await sql<ContextRow[]>`
    select detail.scope_key, detail.model_version, max(detail.calculated_at) as calculated_at,
           competition.code as competition_code, competition.name as competition_name,
           season.label as season_label
    from analytics.product_team_detail_v2 as detail
    join football.seasons as season on season.id = detail.season_id
    join football.competitions as competition on competition.id = season.competition_id
    where (${competitionCode} = '' or competition.code = ${competitionCode})
      and (${seasonLabel} = '' or season.label = ${seasonLabel})
    group by detail.scope_key, detail.model_version, competition.code, competition.name, season.label
    order by max(detail.calculated_at) desc
    limit 1
  `;
  return rows[0] ? context(rows[0]) : null;
}

function mapTeamRanking(row: RankingRow, dimension: TeamRankingDimension): ProductTeamRanking {
  const evidence = dimensions(row.dimension_evidence)[dimension];
  return {
    teamId: numberValue(row.entity_id),
    teamName: row.entity_name,
    competitionCode: row.competition_code ?? "",
    competitionName: row.competition_name ?? "",
    seasonLabel: row.season_label ?? "",
    matches: numberValue(row.matches),
    score: numberValue(row.ranking_score),
    confidence: numberValue(row.confidence),
    evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
    dimension,
    keyEvidence: evidence?.availableMetrics.slice(0, 3) ?? [],
  };
}

export async function getProductTeamRankings(
  filters: TeamRankingFilters,
): Promise<DataResult<{ context: ProductContext | null; teams: ProductTeamRanking[] }>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await latestTeamContext(sql, filters.competitionCode, filters.seasonLabel);
    if (!active) return { status: "ready", data: { context: null, teams: [] } };
    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<RankingRow[]>`
      select score.team_id as entity_id, team.name as entity_name, null::text as team_name,
             competition.code as competition_code, competition.name as competition_name,
             season.label as season_label, null::text as role, null::text as position_family,
             null::integer as minutes, null::integer as appearances, score.matches,
             case when ${filters.dimension} = 'overall' then score.overall_score
                  else nullif(score.dimension_evidence -> ${filters.dimension} ->> 'score', '')::numeric
             end as ranking_score,
             score.confidence, score.evidence_coverage_pct, score.dimension_evidence
      from analytics.product_team_ranking_candidates_v2 as score
      join football.teams as team on team.id = score.team_id
      join football.seasons as season on season.id = score.season_id
      join football.competitions as competition on competition.id = season.competition_id
      where score.window_key = ${filters.window}
        and score.scope_key = ${active.scopeKey}
        and score.model_version = ${active.modelVersion}
        and score.confidence >= ${Math.max(0.4, filters.minConfidence)}
        and (${filters.competitionCode} = '' or competition.code = ${filters.competitionCode})
        and (${filters.seasonLabel} = '' or season.label = ${filters.seasonLabel})
        and (${filters.search.trim()} = '' or team.name ilike ${pattern})
        and (
          (${filters.dimension} = 'overall' and score.evidence_state = 'ready'
            and score.overall_score is not null)
          or
          (${filters.dimension} <> 'overall'
            and score.dimension_evidence -> ${filters.dimension} ->> 'evidence_state' = 'ready'
            and score.dimension_evidence -> ${filters.dimension} ->> 'score' is not null)
        )
      order by ranking_score desc, score.confidence desc, team.name
      limit ${filters.limit}
    `;
    return {
      status: "ready",
      data: { context: active, teams: rows.map((row) => mapTeamRanking(row, filters.dimension)) },
    };
  } catch {
    return failed();
  }
}

export interface ProductTeamDirectoryEntry {
  teamId: number;
  teamName: string;
  competitionCode: string;
  competitionName: string;
  seasonLabel: string;
  matches: number;
}

/**
 * The real teams with certified Team V2 evidence in the active scope, with
 * NO confidence/ready-dimension/score gate -- deliberately not a ranking.
 * Used by `/team-rankings` (and reused by Home) to give a real user a path
 * into `/team/{id}` when the confidence-gated ranking candidates view
 * (`product_team_ranking_candidates_v2`) is correctly empty. Reads only
 * `analytics.product_team_detail_v2` (already scoped to `data_context =
 * 'real'` and `model_version = 'team-v2.0'` by the view itself -- never
 * V1/test_smoke), one row per team (`window_key = 'season'`), ordered
 * alphabetically for a deterministic, non-performance order.
 */
export async function getProductTeamDirectory(
  competitionCode = "",
  seasonLabel = "",
): Promise<DataResult<{ context: ProductContext | null; teams: ProductTeamDirectoryEntry[] }>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await latestTeamContext(sql, competitionCode, seasonLabel);
    if (!active) return { status: "ready", data: { context: null, teams: [] } };
    const rows = await sql<Array<{
      team_id: string | number;
      team_name: string;
      competition_code: string;
      competition_name: string;
      season_label: string;
      matches: string | number | null;
    }>>`
      select score.team_id, team.name as team_name,
             competition.code as competition_code, competition.name as competition_name,
             season.label as season_label, score.matches
      from analytics.product_team_detail_v2 as score
      join football.teams as team on team.id = score.team_id
      join football.seasons as season on season.id = score.season_id
      join football.competitions as competition on competition.id = season.competition_id
      where score.scope_key = ${active.scopeKey}
        and score.model_version = ${active.modelVersion}
        and score.window_key = 'season'
      order by team.name
    `;
    return {
      status: "ready",
      data: {
        context: active,
        teams: rows.map((row) => ({
          teamId: numberValue(row.team_id),
          teamName: row.team_name,
          competitionCode: row.competition_code,
          competitionName: row.competition_name,
          seasonLabel: row.season_label,
          matches: numberValue(row.matches),
        })),
      },
    };
  } catch {
    return failed();
  }
}

export async function getProductTeamDetail(
  teamId: number,
): Promise<DataResult<ProductTeamDetail | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const contextRows = await sql<ContextRow[]>`
      select detail.scope_key, detail.model_version, max(detail.calculated_at) as calculated_at,
             competition.code as competition_code, competition.name as competition_name,
             season.label as season_label
      from analytics.product_team_detail_v2 as detail
      join football.seasons as season on season.id = detail.season_id
      join football.competitions as competition on competition.id = season.competition_id
      where detail.team_id = ${teamId}
      group by detail.scope_key, detail.model_version, competition.code, competition.name, season.label
      order by max(detail.calculated_at) desc
      limit 1
    `;
    const active = contextRows[0];
    if (!active) return { status: "ready", data: null };
    const [teamRows, scoreRows, metricRows] = await Promise.all([
      sql<Array<{ team_id: string | number; team_name: string }>>`
        select id as team_id, name as team_name from football.teams where id = ${teamId}
      `,
      sql<ScoreRow[]>`
        select window_key, 'midfielder'::text as role, null::text as position_family,
               0 as minutes, 0 as appearances, matches, overall_score, confidence,
               evidence_coverage_pct, evidence_state, dimension_evidence, diagnostics, calculated_at
        from analytics.product_team_detail_v2
        where team_id = ${teamId}
          and scope_key = ${active.scope_key}
          and model_version = ${active.model_version}
        order by case window_key
          when 'season' then 1 when 'last_10' then 2 when 'last_5' then 3 else 4 end
      `,
      sql<MetricRow[]>`
        select window_key, metric_name, metric_unit, metric_kind,
               null::text as metric_granularity, raw_value, null::numeric as per90_value,
               adjusted_value, percentile, null::text as percentile_state,
               comparison_group, reference_sample_size
        from analytics.team_feature_snapshots
        where team_id = ${teamId}
          and scope_key = ${active.scope_key}
          and model_version = ${active.model_version}
          and data_context = 'real'
        order by window_key, metric_name
      `,
    ]);
    const team = teamRows[0];
    if (!team) return { status: "ready", data: null };
    const grouped = { season: [], last_10: [], last_5: [], last_3: [] } as Record<
      TeamWindow,
      ProductMetric[]
    >;
    for (const row of metricRows) {
      grouped[row.window_key].push({
        metricName: row.metric_name,
        metricUnit: row.metric_unit,
        metricKind: row.metric_kind,
        metricGranularity: "team_match",
        rawValue: nullableNumber(row.raw_value),
        per90Value: null,
        adjustedValue: nullableNumber(row.adjusted_value),
        percentile: nullableNumber(row.percentile),
        percentileState: row.percentile === null ? "not_applicable" : "ready",
        comparisonGroup: row.comparison_group,
        referenceSampleSize: numberValue(row.reference_sample_size),
      });
    }
    return {
      status: "ready",
      data: {
        context: context(active),
        team: { teamId: numberValue(team.team_id), teamName: team.team_name },
        windows: scoreRows.map((row) => ({
          window: row.window_key,
          matches: numberValue(row.matches),
          overallScore: nullableNumber(row.overall_score),
          confidence: numberValue(row.confidence),
          evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
          evidenceState: row.evidence_state,
          dimensions: dimensions(row.dimension_evidence),
          diagnostics: diagnostics(row.diagnostics),
          calculatedAt: isoValue(row.calculated_at),
        })),
        metrics: grouped,
      },
    };
  } catch {
    return failed();
  }
}

/**
 * Reads only diagnostic findings that are themselves proven product-safe --
 * `data_context = 'real'` and `source_model_version` matching the
 * corresponding V2 statistical model, scoped to whichever snapshot is
 * currently active (see `analytics.product_player_diagnostic_findings_v2` /
 * `product_team_diagnostic_findings_v2`). Entity existence in a V2 detail
 * view is never sufficient on its own: a legacy/smoke finding for the same
 * entity_id must stay hidden even though the entity itself is real.
 */
async function productDiagnostics(
  sql: Sql,
  entityType: "player" | "team" | "all",
  codes: string[],
  limit: number,
): Promise<ProductDiagnostic[]> {
  const rows = await sql<DiagnosticRow[]>`
    select finding.diagnostic_code, finding.entity_type, finding.entity_id,
           coalesce(player.display_name, team.name, 'Entidad') as entity_name,
           finding.severity, finding.confidence, finding.supporting_metrics,
           finding.window_key, finding.model_version
    from (
      select * from analytics.product_player_diagnostic_findings_v2
      union all
      select * from analytics.product_team_diagnostic_findings_v2
    ) as finding
    left join football.players as player
      on finding.entity_type = 'player' and player.id = finding.entity_id
    left join football.teams as team
      on finding.entity_type = 'team' and team.id = finding.entity_id
    where (${entityType} = 'all' or finding.entity_type = ${entityType})
      and finding.diagnostic_code = any(${codes})
      and finding.supporting_metrics <> '{}'::jsonb
    order by finding.confidence desc, finding.computed_at desc
    limit ${limit}
  `;
  return rows.map((row) => ({
    diagnosticCode: row.diagnostic_code,
    entityType: row.entity_type,
    entityId: numberValue(row.entity_id),
    entityName: row.entity_name,
    severity: row.severity,
    confidence: numberValue(row.confidence),
    supportingMetrics: objectValue(row.supporting_metrics),
    window: row.window_key,
    modelVersion: row.model_version,
  }));
}

export async function getResultsVsPerformance(): Promise<
  DataResult<{ player: ProductDiagnostic[]; team: ProductDiagnostic[] }>
> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const [player, team] = await Promise.all([
      productDiagnostics(
        sql,
        "player",
        ["finishing_underperformance", "finishing_overperformance"],
        100,
      ),
      productDiagnostics(
        sql,
        "team",
        ["results_above_process", "results_below_process", "regression_risk"],
        100,
      ),
    ]);
    return { status: "ready", data: { player, team } };
  } catch {
    return failed();
  }
}

export async function getProductHome(): Promise<DataResult<ProductHomeData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const playerBase: PlayerRankingFilters = {
      competitionCode: "",
      seasonLabel: "",
      window: "season",
      positionFamily: "all",
      minMinutes: 450,
      minConfidence: 0.4,
      search: "",
      dimension: "overall",
      limit: 4,
    };
    const teamBase: TeamRankingFilters = {
      competitionCode: "",
      seasonLabel: "",
      window: "season",
      minConfidence: 0.4,
      search: "",
      dimension: "overall",
      limit: 4,
    };
    const [players, form, teams, nowSignals, surprises, disappointments, teamSignals, watchlist] =
      await Promise.all([
        getProductPlayerRankings(playerBase),
        getProductPlayerRankings({ ...playerBase, window: "last_5", minMinutes: 180 }),
        getProductTeamRankings(teamBase),
        productDiagnostics(sql, "all", [
          "finishing_underperformance",
          "finishing_overperformance",
          "results_above_process",
          "results_below_process",
        ], 6),
        productDiagnostics(sql, "player", ["finishing_overperformance"], 4),
        productDiagnostics(sql, "player", ["finishing_underperformance"], 4),
        productDiagnostics(sql, "team", [
          "creation_problem",
          "defensive_process_strong",
          "defensive_process_weak",
          "sterile_possession",
        ], 4),
        getWatchlistData(),
      ]);
    return {
      status: "ready",
      data: {
        context: players.status === "ready" ? players.data.context : null,
        bestPlayers: players.status === "ready" ? players.data.players : [],
        bestTeams: teams.status === "ready" ? teams.data.teams : [],
        formPlayers: form.status === "ready" ? form.data.players : [],
        nowSignals,
        surprises,
        disappointments,
        underrated: [],
        overrated: [],
        watchlist: watchlist.status === "ready" ? watchlist.data.entries.slice(0, 4) : [],
        teamSignals,
      },
    };
  } catch {
    return failed();
  }
}

export async function getCompareOptions(): Promise<
  DataResult<{ players: CompareOption[]; teams: CompareOption[] }>
> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const [players, teams] = await Promise.all([
      sql<Array<{ id: string | number; name: string; subtitle: string }>>`
        select distinct player.id, player.display_name as name,
               coalesce(score.position_family, score.role) as subtitle
        from analytics.product_player_detail_v2 as score
        join football.players as player on player.id = score.player_id
        order by name
      `,
      sql<Array<{ id: string | number; name: string; subtitle: string }>>`
        select distinct team.id, team.name,
               competition.name || ' · ' || season.label as subtitle
        from analytics.product_team_detail_v2 as score
        join football.teams as team on team.id = score.team_id
        join football.seasons as season on season.id = score.season_id
        join football.competitions as competition on competition.id = season.competition_id
        order by name
      `,
    ]);
    const map = (row: { id: string | number; name: string; subtitle: string }) => ({
      id: numberValue(row.id),
      name: row.name,
      subtitle: row.subtitle,
    });
    return { status: "ready", data: { players: players.map(map), teams: teams.map(map) } };
  } catch {
    return failed();
  }
}

export async function getWatchlistData(): Promise<DataResult<WatchlistData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const [entries, candidates, automaticSuggestions] = await Promise.all([
      sql<Array<{
        player_id: string | number;
        display_name: string;
        team_name: string | null;
        category: string;
        reason: string | null;
        created_at: Date | string;
        overall_score: string | number | null;
        confidence: string | number;
        evidence_state: ScoreEvidenceState;
      }>>`
        select entry.player_id, player.display_name, latest_team.team_name,
               entry.category, entry.reason, entry.created_at,
               score.overall_score, score.confidence, score.evidence_state
        from analytics.product_player_watchlist_v2 as entry
        join football.players as player on player.id = entry.player_id
        join lateral (
          select overall_score, confidence, evidence_state
          from analytics.product_player_detail_v2
          where player_id = entry.player_id and window_key = 'season'
          order by calculated_at desc
          limit 1
        ) as score on true
        left join lateral (
          select team.name as team_name
          from football.player_appearances as appearance
          join football.matches as match on match.id = appearance.match_id
          join football.teams as team on team.id = appearance.team_id
          where appearance.player_id = entry.player_id
          order by match.kickoff_at desc nulls last
          limit 1
        ) as latest_team on true
        order by entry.created_at desc
      `,
      sql<Array<{ id: string | number; name: string; subtitle: string }>>`
        select distinct player.id, player.display_name as name,
               coalesce(score.position_family, score.role) as subtitle
        from analytics.product_player_detail_v2 as score
        join football.players as player on player.id = score.player_id
        where not exists (
          select 1 from analytics.player_watchlist_entries as entry
          where entry.player_id = score.player_id
        )
        order by name
        limit 100
      `,
      productDiagnostics(sql, "player", ["finishing_underperformance"], 8),
    ]);
    return {
      status: "ready",
      data: {
        entries: entries.map((row) => ({
          playerId: numberValue(row.player_id),
          playerName: row.display_name,
          teamName: row.team_name,
          category: row.category,
          reason: row.reason,
          createdAt: isoValue(row.created_at),
          score: nullableNumber(row.overall_score),
          confidence: numberValue(row.confidence),
          evidenceState: row.evidence_state,
        })),
        candidates: candidates.map((row) => ({
          id: numberValue(row.id),
          name: row.name,
          subtitle: row.subtitle,
        })),
        automaticSuggestions,
      },
    };
  } catch {
    return failed();
  }
}
