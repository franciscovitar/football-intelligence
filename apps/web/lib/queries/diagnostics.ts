import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export type DiagnosticEntityType = "player" | "team";
export type DiagnosticSeverity = "info" | "notable" | "high";

/**
 * `supporting_metrics` is a flat jsonb object (numbers, strings, booleans) --
 * never a nested structure. Consumers read individual fields defensively
 * (see `lib/diagnostics-display.ts`) since the exact key set differs per
 * `diagnosticCode` and a row's absence of a field is a normal, expected
 * state, never an error.
 */
export type SupportingMetrics = Record<string, unknown>;

export interface DiagnosticFinding {
  diagnosticCode: string;
  entityType: DiagnosticEntityType;
  entityId: number;
  severity: DiagnosticSeverity;
  confidence: number;
  supportingMetrics: SupportingMetrics;
  comparisonGroup: string;
  windowKey: string;
  modelVersion: string;
  computedAt: string;
}

interface DbDiagnosticRow {
  diagnostic_code: string;
  entity_type: DiagnosticEntityType;
  entity_id: string | number;
  severity: DiagnosticSeverity;
  confidence: string | number;
  supporting_metrics: unknown;
  comparison_group: string;
  window_key: string;
  model_version: string;
  computed_at: Date | string;
}

function numberValue(value: string | number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function supportingMetrics(value: unknown): SupportingMetrics {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as SupportingMetrics;
}

function mapFinding(row: DbDiagnosticRow): DiagnosticFinding {
  return {
    diagnosticCode: row.diagnostic_code,
    entityType: row.entity_type,
    entityId: numberValue(row.entity_id),
    severity: row.severity,
    confidence: numberValue(row.confidence),
    supportingMetrics: supportingMetrics(row.supporting_metrics),
    comparisonGroup: row.comparison_group,
    windowKey: row.window_key,
    modelVersion: row.model_version,
    computedAt: isoValue(row.computed_at),
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. Diagnósticos leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudieron leer los diagnósticos.",
  };
}

/**
 * A row's absence for a given `(entityType, entityId)` is a valid, correct
 * state -- no rule cleared its threshold for this entity in this window. It
 * is never an error and must never be rendered as a fake "sin problemas"
 * verdict.
 *
 * Reads only from the product-safe views (`data_context = 'real'`, matching
 * `source_model_version`, active scope -- see
 * `20260815130000_isolate_diagnostic_findings_v2_context.sql`), never the
 * raw `analytics.diagnostic_findings` table: entity existence alone is not
 * proof that a given finding is itself real V2 evidence.
 */
export async function getEntityDiagnostics(
  entityType: DiagnosticEntityType,
  entityId: number,
): Promise<DataResult<DiagnosticFinding[]>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbDiagnosticRow[]>`
      select *
      from (
        select * from analytics.product_player_diagnostic_findings_v2
        union all
        select * from analytics.product_team_diagnostic_findings_v2
      ) as finding
      where entity_type = ${entityType}
        and entity_id = ${entityId}
      order by
        case severity when 'high' then 3 when 'notable' then 2 else 1 end desc,
        confidence desc,
        diagnostic_code
    `;
    return { status: "ready", data: rows.map(mapFinding) };
  } catch {
    return failed();
  }
}

/**
 * Top player-level findings for one `diagnosticCode` across all players --
 * used for home-page discovery strips (Sorpresas, Infravalorados,
 * Sobrevalorados). `supportingMetrics.player_name` already carries the
 * display name, so no join back to `football.players` is needed.
 */
export async function getTopPlayerDiagnosticsByCode(
  code: string,
  limit: number,
): Promise<DataResult<DiagnosticFinding[]>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbDiagnosticRow[]>`
      select *
      from analytics.product_player_diagnostic_findings_v2
      where diagnostic_code = ${code}
      order by
        case severity when 'high' then 3 when 'notable' then 2 else 1 end desc,
        confidence desc
      limit ${limit}
    `;
    return { status: "ready", data: rows.map(mapFinding) };
  } catch {
    return failed();
  }
}
