import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export type CoverageState =
  | "current_available"
  | "historical_only"
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

export interface CoverageData {
  cells: CoverageCell[];
  competitionCodes: string[];
  providers: CoverageProvider[];
  lastCheckedAt: string | null;
  totalSnapshotRows: number;
}

const STATE_KEYS: CoverageState[] = [
  "current_available",
  "historical_only",
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

    return {
      status: "ready",
      data: {
        cells,
        competitionCodes,
        providers: Array.from(providerMap.values()),
        lastCheckedAt,
        totalSnapshotRows: cells.reduce((sum, cell) => sum + cell.totalMetrics, 0),
      },
    };
  } catch {
    return failed();
  }
}

export function dominantState(counts: Record<CoverageState, number>): CoverageState {
  let best: CoverageState = "not_probed";
  let bestCount = -1;
  for (const key of STATE_KEYS) {
    const value = counts[key];
    if (value > bestCount) {
      bestCount = value;
      best = key;
    }
  }
  return best;
}
