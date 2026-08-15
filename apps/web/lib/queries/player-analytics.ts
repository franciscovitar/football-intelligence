import { getDatabase } from "@/lib/db/postgres";
import { classifyPositionFamily, type PositionFamily } from "@/lib/position-family";

export type AnalyticsWindow = "season" | "last_10" | "last_5" | "last_3";
export type PlayerRole = "goalkeeper" | "defender" | "midfielder" | "forward";

export type DataResult<T> =
  | { status: "ready"; data: T }
  | { status: "unconfigured"; message: string }
  | { status: "error"; message: string };

export interface SnapshotContext {
  scopeKey: string;
  modelVersion: string;
  calculatedAt: string;
}

export interface RankingPlayer {
  playerId: number;
  playerName: string;
  role: PlayerRole;
  roleConfidence: number;
  minutes: number;
  appearances: number;
  overallScore: number;
  confidence: number;
  dimensionScores: Record<string, number>;
}

export interface TrendPlayer extends RankingPlayer {
  seasonScore: number;
  formScore: number;
  delta: number;
}

export interface HomeDashboard {
  context: SnapshotContext | null;
  performanceLeaders: RankingPlayer[];
  formLeaders: RankingPlayer[];
  risingPlayers: TrendPlayer[];
}

export interface RankingsFilters {
  window: AnalyticsWindow;
  role: PlayerRole | "all";
  minConfidence: number;
  search: string;
  limit: number;
  positionFamily: PositionFamily | "all";
}

export interface RankingPlayerWithPosition extends RankingPlayer {
  listedPosition: string | null;
  positionFamily: PositionFamily | null;
}

export interface RankingsData {
  context: SnapshotContext | null;
  filters: RankingsFilters;
  players: RankingPlayerWithPosition[];
}

export interface PlayerWindowScore {
  window: AnalyticsWindow;
  role: PlayerRole;
  roleConfidence: number;
  minutes: number;
  appearances: number;
  overallScore: number;
  confidence: number;
  dimensionScores: Record<string, number>;
  calculatedAt: string;
}

export interface PlayerFeature {
  window: AnalyticsWindow;
  role: PlayerRole;
  metricName: string;
  minutes: number;
  appearances: number;
  rawPer90: number;
  adjustedPer90: number;
  percentile: number;
  referenceSampleSize: number;
}

export interface PlayerDetail {
  context: SnapshotContext;
  player: {
    playerId: number;
    playerName: string;
    nationalityCode: string | null;
    dateOfBirth: string | null;
    latestTeam: string | null;
  };
  scores: PlayerWindowScore[];
  features: PlayerFeature[];
}

export interface LabContextSummary {
  scopeKey: string;
  modelVersion: string;
  calculatedAt: string;
  scoreRows: number;
  players: number;
}

export interface LabPopulation {
  window: AnalyticsWindow;
  role: PlayerRole;
  players: number;
  averageConfidence: number;
  averageScore: number;
}

export interface LabMetric {
  metricName: string;
  featureRows: number;
  players: number;
  averageReferenceSample: number;
}

export interface LabData {
  activeContext: SnapshotContext | null;
  contexts: LabContextSummary[];
  populations: LabPopulation[];
  metrics: LabMetric[];
}

interface DbContextRow {
  scope_key: string;
  model_version: string;
  calculated_at: Date | string;
}

interface DbRankingRow {
  player_id: string | number;
  display_name: string;
  role: PlayerRole;
  role_confidence: string | number;
  minutes: string | number;
  appearances: string | number;
  overall_score: string | number;
  confidence: string | number;
  dimension_scores: unknown;
}

interface DbRankingRowWithPosition extends DbRankingRow {
  listed_position: string | null;
}

interface DbTrendRow extends DbRankingRow {
  season_score: string | number;
  form_score: string | number;
  delta: string | number;
}

interface DbPlayerRow {
  player_id: string | number;
  display_name: string;
  nationality_code: string | null;
  date_of_birth: Date | string | null;
  latest_team: string | null;
}

interface DbPlayerScoreRow extends DbRankingRow {
  window_key: AnalyticsWindow;
  calculated_at: Date | string;
}

interface DbFeatureRow {
  window_key: AnalyticsWindow;
  role: PlayerRole;
  metric_name: string;
  minutes: string | number;
  appearances: string | number;
  raw_per90: string | number;
  adjusted_per90: string | number;
  percentile: string | number;
  reference_sample_size: string | number;
}

interface DbLabContextRow extends DbContextRow {
  score_rows: string | number;
  players: string | number;
}

interface DbPopulationRow {
  window_key: AnalyticsWindow;
  role: PlayerRole;
  players: string | number;
  average_confidence: string | number;
  average_score: string | number;
}

interface DbMetricRow {
  metric_name: string;
  feature_rows: string | number;
  players: string | number;
  average_reference_sample: string | number;
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message:
      "DATABASE_URL no está configurada. La interfaz está lista para leer los snapshots reales cuando conectemos PostgreSQL.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message:
      "No se pudo leer el modelo analítico. Revisá la conexión de PostgreSQL o el estado del pipeline.",
  };
}

function numberValue(value: string | number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isoValue(value: Date | string): string {
  if (value instanceof Date) {
    return value.toISOString();
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
}

function dateValue(value: Date | string | null): string | null {
  if (value === null) {
    return null;
  }

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  return String(value).slice(0, 10);
}

function dimensionScores(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  const result: Record<string, number> = {};

  for (const [key, candidate] of Object.entries(value)) {
    const parsed = Number(candidate);
    if (Number.isFinite(parsed)) {
      result[key] = parsed;
    }
  }

  return result;
}

function mapRanking(row: DbRankingRow): RankingPlayer {
  return {
    playerId: numberValue(row.player_id),
    playerName: row.display_name,
    role: row.role,
    roleConfidence: numberValue(row.role_confidence),
    minutes: numberValue(row.minutes),
    appearances: numberValue(row.appearances),
    overallScore: numberValue(row.overall_score),
    confidence: numberValue(row.confidence),
    dimensionScores: dimensionScores(row.dimension_scores),
  };
}

async function latestContext(
  sql: NonNullable<ReturnType<typeof getDatabase>>,
): Promise<SnapshotContext | null> {
  const rows = await sql<DbContextRow[]>`
    select
      scope_key,
      model_version,
      max(calculated_at) as calculated_at
    from analytics.player_score_snapshots
    group by scope_key, model_version
    order by max(calculated_at) desc
    limit 1
  `;

  const row = rows[0];

  if (!row) {
    return null;
  }

  return {
    scopeKey: row.scope_key,
    modelVersion: row.model_version,
    calculatedAt: isoValue(row.calculated_at),
  };
}

async function topPlayers(
  sql: NonNullable<ReturnType<typeof getDatabase>>,
  context: SnapshotContext,
  window: AnalyticsWindow,
  limit: number,
): Promise<RankingPlayer[]> {
  const rows = await sql<DbRankingRow[]>`
    select
      p.id as player_id,
      p.display_name,
      s.role,
      s.role_confidence,
      s.minutes,
      s.appearances,
      s.overall_score,
      s.confidence,
      s.dimension_scores
    from analytics.player_score_snapshots as s
    join football.players as p
      on p.id = s.player_id
    where s.scope_key = ${context.scopeKey}
      and s.model_version = ${context.modelVersion}
      and s.window_key = ${window}
      and s.confidence >= 0.25
    order by s.overall_score desc, s.confidence desc, p.display_name
    limit ${limit}
  `;

  return rows.map(mapRanking);
}

export async function getHomeDashboard(): Promise<DataResult<HomeDashboard>> {
  const sql = getDatabase();

  if (!sql) {
    return unconfigured();
  }

  try {
    const context = await latestContext(sql);

    if (!context) {
      return {
        status: "ready",
        data: {
          context: null,
          performanceLeaders: [],
          formLeaders: [],
          risingPlayers: [],
        },
      };
    }

    const [performanceLeaders, formLeaders, trendRows] = await Promise.all([
      topPlayers(sql, context, "season", 6),
      topPlayers(sql, context, "last_5", 6),
      sql<DbTrendRow[]>`
        select
          p.id as player_id,
          p.display_name,
          form.role,
          form.role_confidence,
          form.minutes,
          form.appearances,
          form.overall_score,
          form.confidence,
          form.dimension_scores,
          season.overall_score as season_score,
          form.overall_score as form_score,
          form.overall_score - season.overall_score as delta
        from analytics.player_score_snapshots as form
        join analytics.player_score_snapshots as season
          on season.player_id = form.player_id
         and season.scope_key = form.scope_key
         and season.model_version = form.model_version
         and season.window_key = 'season'
        join football.players as p
          on p.id = form.player_id
        where form.scope_key = ${context.scopeKey}
          and form.model_version = ${context.modelVersion}
          and form.window_key = 'last_5'
          and form.confidence >= 0.25
          and season.confidence >= 0.25
        order by delta desc, form.overall_score desc
        limit 6
      `,
    ]);

    return {
      status: "ready",
      data: {
        context,
        performanceLeaders,
        formLeaders,
        risingPlayers: trendRows.map((row) => ({
          ...mapRanking(row),
          seasonScore: numberValue(row.season_score),
          formScore: numberValue(row.form_score),
          delta: numberValue(row.delta),
        })),
      },
    };
  } catch {
    return failed();
  }
}

export async function getRankings(
  filters: RankingsFilters,
): Promise<DataResult<RankingsData>> {
  const sql = getDatabase();

  if (!sql) {
    return unconfigured();
  }

  try {
    const context = await latestContext(sql);

    if (!context) {
      return {
        status: "ready",
        data: {
          context: null,
          filters,
          players: [],
        },
      };
    }

    const searchPattern = `%${filters.search.trim()}%`;

    // `listed_position` -> position-family classification happens in JS
    // (`classifyPositionFamily`), not SQL, to avoid duplicating the alias
    // table as a CASE expression. Because the filter runs after the SQL
    // LIMIT would otherwise apply, fetch a wider batch whenever a specific
    // family is requested and slice down to `filters.limit` afterward --
    // simpler than pushing the alias table into SQL, at the cost of not
    // being a perfectly exhaustive scan for very narrow families.
    const fetchLimit =
      filters.positionFamily === "all" ? filters.limit : Math.min(filters.limit * 4, 400);

    const rows = await sql<DbRankingRowWithPosition[]>`
      select
        p.id as player_id,
        p.display_name,
        s.role,
        s.role_confidence,
        s.minutes,
        s.appearances,
        s.overall_score,
        s.confidence,
        s.dimension_scores,
        latest_position.listed_position
      from analytics.player_score_snapshots as s
      join football.players as p
        on p.id = s.player_id
      left join lateral (
        select pa.listed_position
        from football.player_appearances as pa
        join football.matches as m
          on m.id = pa.match_id
        where pa.player_id = p.id
          and pa.listed_position is not null
        order by m.kickoff_at desc nulls last
        limit 1
      ) as latest_position on true
      where s.scope_key = ${context.scopeKey}
        and s.model_version = ${context.modelVersion}
        and s.window_key = ${filters.window}
        and (${filters.role} = 'all' or s.role = ${filters.role})
        and s.confidence >= ${filters.minConfidence}
        and (${filters.search.trim()} = '' or p.display_name ilike ${searchPattern})
      order by s.overall_score desc, s.confidence desc, p.display_name
      limit ${fetchLimit}
    `;

    const withPosition: RankingPlayerWithPosition[] = rows.map((row) => ({
      ...mapRanking(row),
      listedPosition: row.listed_position,
      positionFamily: classifyPositionFamily(row.listed_position),
    }));

    const filtered =
      filters.positionFamily === "all"
        ? withPosition
        : withPosition.filter((player) => player.positionFamily === filters.positionFamily);

    return {
      status: "ready",
      data: {
        context,
        filters,
        players: filtered.slice(0, filters.limit),
      },
    };
  } catch {
    return failed();
  }
}

export async function getPlayerDetail(
  playerId: number,
): Promise<DataResult<PlayerDetail | null>> {
  const sql = getDatabase();

  if (!sql) {
    return unconfigured();
  }

  try {
    const context = await latestContext(sql);

    if (!context) {
      return { status: "ready", data: null };
    }

    const playerRows = await sql<DbPlayerRow[]>`
      select
        p.id as player_id,
        p.display_name,
        p.nationality_code,
        p.date_of_birth,
        latest_team.team_name as latest_team
      from football.players as p
      left join lateral (
        select t.name as team_name
        from football.player_appearances as pa
        join football.matches as m
          on m.id = pa.match_id
        join football.teams as t
          on t.id = pa.team_id
        where pa.player_id = p.id
        order by m.kickoff_at desc nulls last
        limit 1
      ) as latest_team on true
      where p.id = ${playerId}
      limit 1
    `;

    const player = playerRows[0];

    if (!player) {
      return { status: "ready", data: null };
    }

    const [scoreRows, featureRows] = await Promise.all([
      sql<DbPlayerScoreRow[]>`
        select
          p.id as player_id,
          p.display_name,
          s.window_key,
          s.role,
          s.role_confidence,
          s.minutes,
          s.appearances,
          s.overall_score,
          s.confidence,
          s.dimension_scores,
          s.calculated_at
        from analytics.player_score_snapshots as s
        join football.players as p
          on p.id = s.player_id
        where s.player_id = ${playerId}
          and s.scope_key = ${context.scopeKey}
          and s.model_version = ${context.modelVersion}
        order by case s.window_key
          when 'last_3' then 1
          when 'last_5' then 2
          when 'last_10' then 3
          when 'season' then 4
          else 5
        end
      `,
      sql<DbFeatureRow[]>`
        select
          window_key,
          role,
          metric_name,
          minutes,
          appearances,
          raw_per90,
          adjusted_per90,
          percentile,
          reference_sample_size
        from analytics.player_feature_snapshots
        where player_id = ${playerId}
          and scope_key = ${context.scopeKey}
          and model_version = ${context.modelVersion}
        order by case window_key
          when 'last_3' then 1
          when 'last_5' then 2
          when 'last_10' then 3
          when 'season' then 4
          else 5
        end,
        percentile desc,
        metric_name
      `,
    ]);

    // A player can be real, identified, and have real evidence (Block 16
    // season-aggregate stats, diagnostic findings) without ever having gone
    // through the V1 per-match scoring pipeline -- e.g. every player in the
    // real ENG_PL 2025/26 snapshot, which has no match-by-match rows for V1
    // to aggregate. Only 404 when the player itself doesn't exist; an empty
    // `scores`/`features` array is a valid, honest state the page must
    // render around, never a reason to hide a real player entirely.

    return {
      status: "ready",
      data: {
        context,
        player: {
          playerId: numberValue(player.player_id),
          playerName: player.display_name,
          nationalityCode: player.nationality_code,
          dateOfBirth: dateValue(player.date_of_birth),
          latestTeam: player.latest_team,
        },
        scores: scoreRows.map((row) => ({
          window: row.window_key,
          role: row.role,
          roleConfidence: numberValue(row.role_confidence),
          minutes: numberValue(row.minutes),
          appearances: numberValue(row.appearances),
          overallScore: numberValue(row.overall_score),
          confidence: numberValue(row.confidence),
          dimensionScores: dimensionScores(row.dimension_scores),
          calculatedAt: isoValue(row.calculated_at),
        })),
        features: featureRows.map((row) => ({
          window: row.window_key,
          role: row.role,
          metricName: row.metric_name,
          minutes: numberValue(row.minutes),
          appearances: numberValue(row.appearances),
          rawPer90: numberValue(row.raw_per90),
          adjustedPer90: numberValue(row.adjusted_per90),
          percentile: numberValue(row.percentile),
          referenceSampleSize: numberValue(row.reference_sample_size),
        })),
      },
    };
  } catch {
    return failed();
  }
}

export async function getLabData(): Promise<DataResult<LabData>> {
  const sql = getDatabase();

  if (!sql) {
    return unconfigured();
  }

  try {
    const activeContext = await latestContext(sql);

    const contexts = await sql<DbLabContextRow[]>`
      select
        scope_key,
        model_version,
        max(calculated_at) as calculated_at,
        count(*) as score_rows,
        count(distinct player_id) as players
      from analytics.player_score_snapshots
      group by scope_key, model_version
      order by max(calculated_at) desc
      limit 12
    `;

    if (!activeContext) {
      return {
        status: "ready",
        data: {
          activeContext: null,
          contexts: [],
          populations: [],
          metrics: [],
        },
      };
    }

    const [populations, metrics] = await Promise.all([
      sql<DbPopulationRow[]>`
        select
          window_key,
          role,
          count(*) as players,
          avg(confidence) as average_confidence,
          avg(overall_score) as average_score
        from analytics.player_score_snapshots
        where scope_key = ${activeContext.scopeKey}
          and model_version = ${activeContext.modelVersion}
        group by window_key, role
        order by window_key, role
      `,
      sql<DbMetricRow[]>`
        select
          metric_name,
          count(*) as feature_rows,
          count(distinct player_id) as players,
          avg(reference_sample_size) as average_reference_sample
        from analytics.player_feature_snapshots
        where scope_key = ${activeContext.scopeKey}
          and model_version = ${activeContext.modelVersion}
          and window_key = 'season'
        group by metric_name
        order by metric_name
      `,
    ]);

    return {
      status: "ready",
      data: {
        activeContext,
        contexts: contexts.map((row) => ({
          scopeKey: row.scope_key,
          modelVersion: row.model_version,
          calculatedAt: isoValue(row.calculated_at),
          scoreRows: numberValue(row.score_rows),
          players: numberValue(row.players),
        })),
        populations: populations.map((row) => ({
          window: row.window_key,
          role: row.role,
          players: numberValue(row.players),
          averageConfidence: numberValue(row.average_confidence),
          averageScore: numberValue(row.average_score),
        })),
        metrics: metrics.map((row) => ({
          metricName: row.metric_name,
          featureRows: numberValue(row.feature_rows),
          players: numberValue(row.players),
          averageReferenceSample: numberValue(row.average_reference_sample),
        })),
      },
    };
  } catch {
    return failed();
  }
}
