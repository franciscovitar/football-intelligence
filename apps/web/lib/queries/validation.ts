import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export interface ValidationSummary {
  modelVersion: string;
  hardStatus: string;
  calibrationStatus: string;
  calculatedAt: string;
  eloSampleSize: number | null;
  eloSkillVsBaseline: number | null;
  playerStabilityMeasuredRoles: string[];
  ratingPrevalence: Record<string, number>;
  tacticalLowCoverageCount: number | null;
  ingestionJobs: string[];
}

interface DbValidationRow {
  model_version: string;
  hard_status: string;
  calibration_status: string;
  calculated_at: Date | string;
  summary: {
    elo_sample_size?: number;
    elo_skill_vs_baseline?: number | null;
    player_stability_measured_roles?: string[];
    rating_prevalence?: Record<string, number>;
    tactical_low_coverage_count?: number;
    ingestion_jobs?: string[];
  };
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message: "DATABASE_URL no está configurada. V1 Validation leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return { status: "error", message: "No se pudo leer V1 Validation." };
}

export async function getLatestValidation(): Promise<DataResult<ValidationSummary | null>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbValidationRow[]>`
      select model_version, hard_status, calibration_status, calculated_at, summary
      from analytics.model_validation_runs
      order by calculated_at desc
      limit 1
    `;
    const latest = rows[0];
    if (!latest) {
      return { status: "ready", data: null };
    }
    const summary = latest.summary ?? {};
    return {
      status: "ready",
      data: {
        modelVersion: latest.model_version,
        hardStatus: latest.hard_status,
        calibrationStatus: latest.calibration_status,
        calculatedAt: isoValue(latest.calculated_at),
        eloSampleSize: summary.elo_sample_size ?? null,
        eloSkillVsBaseline: summary.elo_skill_vs_baseline ?? null,
        playerStabilityMeasuredRoles: summary.player_stability_measured_roles ?? [],
        ratingPrevalence: summary.rating_prevalence ?? {},
        tacticalLowCoverageCount: summary.tactical_low_coverage_count ?? null,
        ingestionJobs: summary.ingestion_jobs ?? [],
      },
    };
  } catch {
    return failed();
  }
}
