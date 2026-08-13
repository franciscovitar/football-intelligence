import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export interface SourceSummary {
  code: string;
  displayName: string;
  isActive: boolean;
  sourceTypes: string[];
  observationCount: number;
  lastObservedAt: string | null;
}

export interface ReconciliationSummary {
  agreedCount: number;
  singleSourceCount: number;
  conflictCount: number;
  unresolvedCount: number;
  lastCalculatedAt: string | null;
}

export interface DataMeshHealth {
  sources: SourceSummary[];
  reconciliation: ReconciliationSummary;
  totalObservations: number;
  totalDecisions: number;
}

interface DbSourceRow {
  code: string;
  display_name: string;
  is_active: boolean;
  source_types: string[];
  observation_count: string | number;
  last_observed_at: Date | string | null;
}

interface DbReconciliationRow {
  status: string;
  status_count: string | number;
  last_calculated_at: Date | string | null;
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
    message: "DATABASE_URL no está configurada. Data Sources leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return { status: "error", message: "No se pudo leer el estado de las fuentes de datos." };
}

export async function getDataMeshHealth(): Promise<DataResult<DataMeshHealth>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const sourceRows = await sql<DbSourceRow[]>`
      select
        p.code,
        p.display_name,
        p.is_active,
        coalesce(
          array_agg(distinct so.source_type) filter (where so.source_type is not null),
          '{}'
        ) as source_types,
        count(so.id) as observation_count,
        max(so.observed_at) as last_observed_at
      from ingestion.providers as p
      left join ingestion.source_observations as so on so.provider_id = p.id
      group by p.code, p.display_name, p.is_active
      order by p.code
    `;

    const reconciliationRows = await sql<DbReconciliationRow[]>`
      select status, count(*) as status_count, max(calculated_at) as last_calculated_at
      from ingestion.reconciliation_decisions
      group by status
    `;

    const byStatus = new Map(reconciliationRows.map((row) => [row.status, row]));
    const countFor = (status: string): number => {
      const row = byStatus.get(status);
      return row ? numberValue(row.status_count) : 0;
    };
    const lastCalculatedAt = reconciliationRows.reduce<string | null>((latest, row) => {
      const value = isoValue(row.last_calculated_at);
      if (!value) return latest;
      return !latest || value > latest ? value : latest;
    }, null);

    const sources = sourceRows.map((row) => ({
      code: row.code,
      displayName: row.display_name,
      isActive: row.is_active,
      sourceTypes: row.source_types ?? [],
      observationCount: numberValue(row.observation_count),
      lastObservedAt: isoValue(row.last_observed_at),
    }));

    return {
      status: "ready",
      data: {
        sources,
        reconciliation: {
          agreedCount: countFor("agreed"),
          singleSourceCount: countFor("single_source"),
          conflictCount: countFor("conflict"),
          unresolvedCount: countFor("unresolved"),
          lastCalculatedAt,
        },
        totalObservations: sources.reduce((sum, item) => sum + item.observationCount, 0),
        totalDecisions: reconciliationRows.reduce((sum, row) => sum + numberValue(row.status_count), 0),
      },
    };
  } catch {
    return failed();
  }
}
