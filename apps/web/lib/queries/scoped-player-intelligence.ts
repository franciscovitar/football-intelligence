import { getDatabase } from "@/lib/db/postgres";
import type { PositionFamily } from "@/lib/position-family";
import type {
  PlayerContextChoice,
} from "@/lib/player-context";
import { parseCompetitionScopeKey } from "@/lib/player-context";
import type {
  PlayerRankingDimension,
  ProductDimensionEvidence,
  ProductMetric,
  ProductPlayerDetail,
  ProductPlayerRanking,
} from "@/lib/queries/product-intelligence";
import type {
  AnalyticsWindow,
  DataResult,
  PlayerRole,
  ScoreEvidenceState,
} from "@/lib/queries/player-analytics";

type Sql = NonNullable<ReturnType<typeof getDatabase>>;

export interface ScopedPlayerContext extends PlayerContextChoice {
  modelVersion: string;
  calculatedAt: string;
}

export interface ScopedPlayerDirectoryEntry {
  playerId: number;
  playerName: string;
  teamName: string | null;
  role: PlayerRole;
  positionFamily: PositionFamily | null;
  minutes: number;
  appearances: number;
  confidence: number;
  evidenceCoveragePct: number;
  evidenceState: ScoreEvidenceState;
  contextScopeKey: string;
}

export interface ScopedPlayerRankingFilters {
  contextScopeKey: string;
  window: AnalyticsWindow;
  positionFamily: PositionFamily | "all";
  minMinutes: number;
  minConfidence: number;
  search: string;
  dimension: PlayerRankingDimension;
  limit: number;
}

export interface ScopedPlayerDirectoryFilters {
  contextScopeKey: string;
  positionFamily: PositionFamily | "all";
  minMinutes: number;
  search: string;
  limit: number;
}

interface ContextRow {
  scope_key: string;
  model_version: string;
  calculated_at: Date | string;
  competition_code: string;
  competition_name: string;
  season_label: string;
  is_current: boolean;
}

interface RankingRow {
  entity_id: string | number;
  entity_name: string;
  team_name: string | null;
  role: PlayerRole;
  position_family: PositionFamily | null;
  minutes: string | number;
  appearances: string | number;
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
  overall_score: string | number | null;
  confidence: string | number;
  evidence_coverage_pct: string | number;
  evidence_state: ScoreEvidenceState;
  dimension_evidence: unknown;
  calculated_at: Date | string;
}

interface MetricRow {
  window_key: AnalyticsWindow;
  metric_name: string;
  metric_unit: string;
  metric_kind: string;
  metric_granularity: string;
  raw_value: string | number | null;
  per90_value: string | number | null;
  adjusted_value: string | number | null;
  percentile: string | number | null;
  percentile_state: string;
  comparison_group: string | null;
  reference_sample_size: string | number;
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
    message: "No pudimos leer el contexto histórico de jugadores V2.",
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

function mapContext(row: ContextRow): ScopedPlayerContext {
  return {
    scopeKey: row.scope_key,
    modelVersion: row.model_version,
    calculatedAt: isoValue(row.calculated_at),
    competitionCode: row.competition_code,
    competitionName: row.competition_name,
    seasonLabel: row.season_label,
    isHistorical: !row.is_current,
  };
}

async function loadContexts(sql: Sql): Promise<ScopedPlayerContext[]> {
  const rows = await sql<ContextRow[]>`
    select
      detail.scope_key,
      detail.model_version,
      max(detail.calculated_at) as calculated_at,
      competition.code as competition_code,
      competition.name as competition_name,
      season.label as season_label,
      season.is_current
    from analytics.product_player_detail_v2 as detail
    join football.competitions as competition
      on split_part(detail.scope_key, ':', 2) = competition.code
    join football.seasons as season
      on season.competition_id = competition.id
     and split_part(detail.scope_key, ':', 3) = season.label
    where split_part(detail.scope_key, ':', 1) = 'competition'
      and array_length(string_to_array(detail.scope_key, ':'), 1) = 3
    group by
      detail.scope_key,
      detail.model_version,
      competition.code,
      competition.name,
      season.label,
      season.is_current,
      season.starts_on,
      season.ends_on
    order by
      coalesce(season.ends_on, season.starts_on) desc nulls last,
      season.starts_on desc nulls last,
      season.label desc,
      competition.code
  `;
  return rows.map(mapContext);
}

async function resolveContext(sql: Sql, requestedScopeKey: string): Promise<ScopedPlayerContext | null> {
  const requested = requestedScopeKey.trim();
  if (requested && parseCompetitionScopeKey(requested) === null) return null;
  const contexts = await loadContexts(sql);
  if (!requested) return contexts[0] ?? null;
  return contexts.find((item) => item.scopeKey === requested) ?? null;
}

export async function getScopedPlayerContexts(): Promise<DataResult<ScopedPlayerContext[]>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    return { status: "ready", data: await loadContexts(sql) };
  } catch {
    return failed();
  }
}

export async function getScopedPlayerRankings(
  filters: ScopedPlayerRankingFilters,
): Promise<DataResult<{ context: ScopedPlayerContext | null; players: ProductPlayerRanking[] }>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await resolveContext(sql, filters.contextScopeKey);
    if (!active) return { status: "ready", data: { context: null, players: [] } };
    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<RankingRow[]>`
      select
        score.player_id as entity_id,
        player.display_name as entity_name,
        selected_team.team_name,
        score.role,
        score.position_family,
        score.minutes,
        score.appearances,
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
        select team.name as team_name
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        join football.seasons as season on season.id = match.season_id
        join football.competitions as competition on competition.id = season.competition_id
        join football.teams as team on team.id = appearance.team_id
        where appearance.player_id = score.player_id
          and competition.code = ${active.competitionCode}
          and season.label = ${active.seasonLabel}
        order by match.kickoff_at desc nulls last, match.id desc
        limit 1
      ) as selected_team on true
      where score.scope_key = ${active.scopeKey}
        and score.model_version = ${active.modelVersion}
        and score.window_key = ${filters.window}
        and score.minutes >= ${filters.minMinutes}
        and score.confidence >= ${Math.max(0.4, filters.minConfidence)}
        and (${filters.positionFamily} = 'all' or score.position_family = ${filters.positionFamily})
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
    const players = rows.map((row): ProductPlayerRanking => {
      const evidence = dimensions(row.dimension_evidence)[filters.dimension];
      return {
        playerId: numberValue(row.entity_id),
        playerName: row.entity_name,
        teamName: row.team_name,
        competitionCode: active.competitionCode,
        competitionName: active.competitionName,
        seasonLabel: active.seasonLabel,
        role: row.role,
        positionFamily: row.position_family,
        minutes: numberValue(row.minutes),
        appearances: numberValue(row.appearances),
        score: numberValue(row.ranking_score),
        confidence: numberValue(row.confidence),
        evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
        dimension: filters.dimension,
        keyEvidence: evidence?.availableMetrics.slice(0, 3) ?? [],
      };
    });
    return { status: "ready", data: { context: active, players } };
  } catch {
    return failed();
  }
}

export async function getScopedPlayerDirectory(
  filters: ScopedPlayerDirectoryFilters,
): Promise<DataResult<{ context: ScopedPlayerContext | null; players: ScopedPlayerDirectoryEntry[] }>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await resolveContext(sql, filters.contextScopeKey);
    if (!active) return { status: "ready", data: { context: null, players: [] } };
    const pattern = `%${filters.search.trim()}%`;
    const rows = await sql<Array<{
      player_id: string | number;
      player_name: string;
      team_name: string | null;
      role: PlayerRole;
      position_family: PositionFamily | null;
      minutes: string | number;
      appearances: string | number;
      confidence: string | number;
      evidence_coverage_pct: string | number;
      evidence_state: ScoreEvidenceState;
    }>>`
      select
        score.player_id,
        player.display_name as player_name,
        selected_team.team_name,
        score.role,
        score.position_family,
        score.minutes,
        score.appearances,
        score.confidence,
        score.evidence_coverage_pct,
        score.evidence_state
      from analytics.product_player_detail_v2 as score
      join football.players as player on player.id = score.player_id
      left join lateral (
        select team.name as team_name
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        join football.seasons as season on season.id = match.season_id
        join football.competitions as competition on competition.id = season.competition_id
        join football.teams as team on team.id = appearance.team_id
        where appearance.player_id = score.player_id
          and competition.code = ${active.competitionCode}
          and season.label = ${active.seasonLabel}
        order by match.kickoff_at desc nulls last, match.id desc
        limit 1
      ) as selected_team on true
      where score.scope_key = ${active.scopeKey}
        and score.model_version = ${active.modelVersion}
        and score.window_key = 'season'
        and score.minutes >= ${filters.minMinutes}
        and (${filters.positionFamily} = 'all' or score.position_family = ${filters.positionFamily})
        and (${filters.search.trim()} = '' or player.display_name ilike ${pattern})
      order by player.display_name
      limit ${filters.limit}
    `;
    return {
      status: "ready",
      data: {
        context: active,
        players: rows.map((row) => ({
          playerId: numberValue(row.player_id),
          playerName: row.player_name,
          teamName: row.team_name,
          role: row.role,
          positionFamily: row.position_family,
          minutes: numberValue(row.minutes),
          appearances: numberValue(row.appearances),
          confidence: numberValue(row.confidence),
          evidenceCoveragePct: numberValue(row.evidence_coverage_pct),
          evidenceState: row.evidence_state,
          contextScopeKey: active.scopeKey,
        })),
      },
    };
  } catch {
    return failed();
  }
}

export async function getScopedPlayerDetail(
  playerId: number,
  contextScopeKey: string,
): Promise<DataResult<ProductPlayerDetail | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await resolveContext(sql, contextScopeKey);
    if (!active) return { status: "ready", data: null };
    const existsRows = await sql<Array<{ player_id: string | number }>>`
      select player_id
      from analytics.product_player_detail_v2
      where player_id = ${playerId}
        and scope_key = ${active.scopeKey}
        and model_version = ${active.modelVersion}
      limit 1
    `;
    if (!existsRows[0]) return { status: "ready", data: null };

    const [playerRows, scoreRows, metricRows] = await Promise.all([
      sql<Array<{
        player_id: string | number;
        display_name: string;
        nationality_code: string | null;
        date_of_birth: Date | string | null;
        team_name: string | null;
      }>>`
        select
          player.id as player_id,
          player.display_name,
          player.nationality_code,
          player.date_of_birth,
          selected_team.team_name
        from football.players as player
        left join lateral (
          select team.name as team_name
          from football.player_appearances as appearance
          join football.matches as match on match.id = appearance.match_id
          join football.seasons as season on season.id = match.season_id
          join football.competitions as competition on competition.id = season.competition_id
          join football.teams as team on team.id = appearance.team_id
          where appearance.player_id = player.id
            and competition.code = ${active.competitionCode}
            and season.label = ${active.seasonLabel}
          order by match.kickoff_at desc nulls last, match.id desc
          limit 1
        ) as selected_team on true
        where player.id = ${playerId}
      `,
      sql<ScoreRow[]>`
        select
          window_key,
          role,
          position_family,
          minutes,
          appearances,
          overall_score,
          confidence,
          evidence_coverage_pct,
          evidence_state,
          dimension_evidence,
          calculated_at
        from analytics.product_player_detail_v2
        where player_id = ${playerId}
          and scope_key = ${active.scopeKey}
          and model_version = ${active.modelVersion}
        order by case window_key
          when 'season' then 1 when 'last_10' then 2 when 'last_5' then 3 else 4 end
      `,
      sql<MetricRow[]>`
        select
          window_key,
          metric_name,
          metric_unit,
          metric_kind,
          metric_granularity,
          raw_value,
          per90_value,
          adjusted_per90 as adjusted_value,
          percentile,
          percentile_state,
          comparison_group,
          reference_sample_size
        from analytics.player_feature_snapshots
        where player_id = ${playerId}
          and scope_key = ${active.scopeKey}
          and model_version = ${active.modelVersion}
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
        metricGranularity: row.metric_granularity,
        rawValue: nullableNumber(row.raw_value),
        per90Value: nullableNumber(row.per90_value),
        adjustedValue: nullableNumber(row.adjusted_value),
        percentile: nullableNumber(row.percentile),
        percentileState: row.percentile_state,
        comparisonGroup: row.comparison_group,
        referenceSampleSize: numberValue(row.reference_sample_size),
      });
    }
    return {
      status: "ready",
      data: {
        context: {
          scopeKey: active.scopeKey,
          modelVersion: active.modelVersion,
          calculatedAt: active.calculatedAt,
          competitionCode: active.competitionCode,
          competitionName: active.competitionName,
          seasonLabel: active.seasonLabel,
        },
        player: {
          playerId: numberValue(player.player_id),
          playerName: player.display_name,
          teamName: player.team_name,
          competitionCode: active.competitionCode,
          competitionName: active.competitionName,
          seasonLabel: active.seasonLabel,
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

export async function getScopedPlayerCompareOptions(
  contextScopeKey: string,
): Promise<DataResult<Array<{ id: number; name: string; subtitle: string }>>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();
  try {
    const active = await resolveContext(sql, contextScopeKey);
    if (!active) return { status: "ready", data: [] };
    const rows = await sql<Array<{
      id: string | number;
      name: string;
      role: PlayerRole;
      position_family: PositionFamily | null;
    }>>`
      select distinct player.id, player.display_name as name, score.role, score.position_family
      from analytics.product_player_detail_v2 as score
      join football.players as player on player.id = score.player_id
      where score.scope_key = ${active.scopeKey}
        and score.model_version = ${active.modelVersion}
        and score.window_key = 'season'
      order by name
    `;
    return {
      status: "ready",
      data: rows.map((row) => ({
        id: numberValue(row.id),
        name: row.name,
        subtitle: `${row.position_family ?? row.role} · ${active.seasonLabel}`,
      })),
    };
  } catch {
    return failed();
  }
}
