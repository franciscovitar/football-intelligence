import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export type CoverageState =
  | "current_available"
  | "historical_only"
  | "previous_season"
  | "partial"
  | "token_required"
  | "not_probed"
  | "missing"
  | "unsupported";

export interface CoverageCell {
  competitionCode: string;
  providerCode: string;
  providerDisplayName: string;
  freshnessRole: "current" | "historical";
  stateCounts: Record<CoverageState, number>;
  totalMetrics: number;
  lastCheckedAt: string | null;
}

export interface CoverageProvider {
  code: string;
  displayName: string;
  freshnessRole: "current" | "historical";
}

export interface ProductCoverageSummary {
  numerator: number;
  denominator: number;
}

export interface CoverageData {
  cells: CoverageCell[];
  competitionCodes: string[];
  providers: CoverageProvider[];
  lastCheckedAt: string | null;
  /** Raw provider x competition x metric rows evaluated -- diagnostic only,
   * scales with provider count. Never the product's metric catalog size. */
  providerEntryCount: number;
  /** Product-level union coverage: satisfied when AT LEAST ONE provider of
   * the relevant freshness role covers the requirement. Denominator is the
   * fixed target catalog (metrics x competitions), independent of how many
   * providers exist. */
  productCurrentCoverage: ProductCoverageSummary;
  /** A `current`-role provider whose probe verified only the latest
   * *completed* season/period (not the TRUE current one, computed from the
   * run date) -- real evidence, but never folded into productCurrentCoverage. */
  productRecentSeasonCoverage: ProductCoverageSummary;
  productHistoricalCoverage: ProductCoverageSummary;
}

// Priority order for the honest per-cell state summary: never a single
// majority-derived verdict, always every non-zero bucket the cell actually
// has, in this fixed order.
const STATE_KEYS: CoverageState[] = [
  "current_available",
  "historical_only",
  "previous_season",
  "partial",
  "token_required",
  "not_probed",
  "missing",
  "unsupported",
];

interface DbCoverageRow {
  competition_code: string;
  provider_code: string;
  provider_display_name: string;
  freshness_role: "current" | "historical";
  current_available_count: string | number;
  historical_only_count: string | number;
  previous_season_count: string | number;
  partial_count: string | number;
  token_required_count: string | number;
  not_probed_count: string | number;
  missing_count: string | number;
  unsupported_count: string | number;
  total_metrics: string | number;
  last_checked_at: Date | string | null;
}

function numberValue(value: string | number): number {
  return Number(value);
}

function isoValue(value: Date | string | null): string | null {
  if (value === null) return null;
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

interface DbProductCoverageRow {
  numerator: string | number;
  denominator: string | number;
}

// Product-level union: group by the requirement identity (competition,
// metric, granularity) -- never metric_name alone, since the same name can
// legitimately exist at two granularities -- and count a requirement as
// satisfied when AT LEAST ONE provider of the given freshness role covers
// it. The denominator is the distinct requirement count, which never grows
// just because more providers exist.
async function getProductCoverage(
  sql: ReturnType<typeof getDatabase>,
  freshnessRole: "current" | "historical",
): Promise<ProductCoverageSummary> {
  const satisfyingState = freshnessRole === "current" ? "current_available" : "historical_only";
  if (!sql) return { numerator: 0, denominator: 0 };

  const rows = await sql<DbProductCoverageRow[]>`
    select
      count(*) filter (where satisfied) as numerator,
      count(*) as denominator
    from (
      select bool_or(state = ${satisfyingState}) as satisfied
      from ingestion.coverage_snapshots
      where freshness_role = ${freshnessRole}
      group by competition_code, metric_name, granularity
    ) as requirements
  `;
  const row = rows[0];
  return {
    numerator: row ? numberValue(row.numerator) : 0,
    denominator: row ? numberValue(row.denominator) : 0,
  };
}

// Same union shape as `getProductCoverage`, but for `previous_season`
// evidence specifically -- always reported separately, never combined with
// or subtracted from the current-role numerator above.
async function getRecentSeasonCoverage(
  sql: ReturnType<typeof getDatabase>,
): Promise<ProductCoverageSummary> {
  if (!sql) return { numerator: 0, denominator: 0 };

  const rows = await sql<DbProductCoverageRow[]>`
    select
      count(*) filter (where satisfied) as numerator,
      count(*) as denominator
    from (
      select bool_or(state = 'previous_season') as satisfied
      from ingestion.coverage_snapshots
      where freshness_role = 'current'
      group by competition_code, metric_name, granularity
    ) as requirements
  `;
  const row = rows[0];
  return {
    numerator: row ? numberValue(row.numerator) : 0,
    denominator: row ? numberValue(row.denominator) : 0,
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. La cobertura se leerá cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return { status: "error", message: "No se pudo leer la cobertura de fuentes." };
}

export async function getCoverageMatrix(): Promise<DataResult<CoverageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbCoverageRow[]>`
      select
        cs.competition_code,
        p.code as provider_code,
        p.display_name as provider_display_name,
        cs.freshness_role,
        count(*) filter (where cs.state = 'current_available') as current_available_count,
        count(*) filter (where cs.state = 'historical_only') as historical_only_count,
        count(*) filter (where cs.state = 'previous_season') as previous_season_count,
        count(*) filter (where cs.state = 'partial') as partial_count,
        count(*) filter (where cs.state = 'token_required') as token_required_count,
        count(*) filter (where cs.state = 'not_probed') as not_probed_count,
        count(*) filter (where cs.state = 'missing') as missing_count,
        count(*) filter (where cs.state = 'unsupported') as unsupported_count,
        count(*) as total_metrics,
        max(cs.last_checked_at) as last_checked_at
      from ingestion.coverage_snapshots as cs
      join ingestion.providers as p on p.id = cs.provider_id
      group by cs.competition_code, p.code, p.display_name, cs.freshness_role
      order by cs.competition_code, p.code
    `;

    const cells: CoverageCell[] = rows.map((row) => ({
      competitionCode: row.competition_code,
      providerCode: row.provider_code,
      providerDisplayName: row.provider_display_name,
      freshnessRole: row.freshness_role,
      stateCounts: {
        current_available: numberValue(row.current_available_count),
        historical_only: numberValue(row.historical_only_count),
        previous_season: numberValue(row.previous_season_count),
        partial: numberValue(row.partial_count),
        token_required: numberValue(row.token_required_count),
        not_probed: numberValue(row.not_probed_count),
        missing: numberValue(row.missing_count),
        unsupported: numberValue(row.unsupported_count),
      },
      totalMetrics: numberValue(row.total_metrics),
      lastCheckedAt: isoValue(row.last_checked_at),
    }));

    const providerMap = new Map<string, CoverageProvider>();
    for (const cell of cells) {
      if (!providerMap.has(cell.providerCode)) {
        providerMap.set(cell.providerCode, {
          code: cell.providerCode,
          displayName: cell.providerDisplayName,
          freshnessRole: cell.freshnessRole,
        });
      }
    }

    const competitionCodes = Array.from(new Set(cells.map((cell) => cell.competitionCode))).sort();
    const lastCheckedAt = cells.reduce<string | null>((latest, cell) => {
      if (!cell.lastCheckedAt) return latest;
      return !latest || cell.lastCheckedAt > latest ? cell.lastCheckedAt : latest;
    }, null);

    const [productCurrentCoverage, productHistoricalCoverage, productRecentSeasonCoverage] =
      await Promise.all([
        getProductCoverage(sql, "current"),
        getProductCoverage(sql, "historical"),
        getRecentSeasonCoverage(sql),
      ]);

    return {
      status: "ready",
      data: {
        cells,
        competitionCodes,
        providers: Array.from(providerMap.values()),
        lastCheckedAt,
        providerEntryCount: cells.reduce((sum, cell) => sum + cell.totalMetrics, 0),
        productCurrentCoverage,
        productRecentSeasonCoverage,
        productHistoricalCoverage,
      },
    };
  } catch {
    return failed();
  }
}

/**
 * Honest per-cell coverage summary: every non-zero state bucket, in a fixed
 * priority order -- never a single majority-derived verdict. A provider
 * that covers 2 of 48 metrics and structurally lacks the other 46 must show
 * both facts, not collapse to a single "NO SOPORTADO" badge that hides the
 * 2 it does cover.
 */
export function summarizeCoverageStates(
  counts: Record<CoverageState, number>,
): { state: CoverageState; count: number }[] {
  return STATE_KEYS.map((state) => ({ state, count: counts[state] })).filter(
    (entry) => entry.count > 0,
  );
}
