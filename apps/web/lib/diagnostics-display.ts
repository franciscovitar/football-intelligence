import type { DiagnosticSeverity, SupportingMetrics } from "@/lib/queries/diagnostics";

export const DIAGNOSTIC_SEVERITY_LABELS: Record<DiagnosticSeverity, string> = {
  info: "Informativo",
  notable: "Notable",
  high: "Alto",
};

export const DIAGNOSTIC_WINDOW_LABELS: Record<string, string> = {
  season: "Temporada",
  stable: "Nivel estable",
  rating: "Rating",
  last_3: "Últimos 3",
  last_5: "Últimos 5",
  last_10: "Últimos 10",
};

function num(metrics: SupportingMetrics, key: string): number | null {
  const value = metrics[key];
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function pct(value: number | null): string {
  return value === null ? "s/d" : `P${Math.round(value)}`;
}

function dec1(value: number | null): string {
  return value === null ? "s/d" : value.toFixed(1);
}

function signed1(value: number | null): string {
  if (value === null) return "s/d";
  const rounded = value.toFixed(1);
  return value > 0 ? `+${rounded}` : rounded;
}

function int(value: number | null): string {
  return value === null ? "s/d" : String(Math.round(value));
}

/**
 * Deterministic template strings per `diagnosticCode` -- data/rules decide,
 * this function only explains in Spanish. Never an LLM call, never
 * fabricates a number not already present in `supportingMetrics`. Codes not
 * in this mapping (e.g. added later by the Python rule engine without a web
 * copy update yet) fall back to a generic, honest sentence instead of
 * crashing or hiding the finding.
 */
export function diagnosticCodeToSentence(code: string, metrics: SupportingMetrics): string {
  switch (code) {
    case "finishing_underperformance":
      return `Convierte por debajo de lo que sugiere su xG: ${dec1(num(metrics, "goals"))} goles (${pct(num(metrics, "goals_percentile"))}) frente a ${dec1(num(metrics, "xg"))} xG (${pct(num(metrics, "xg_percentile"))}).`;
    case "finishing_overperformance":
      return `Convierte por encima de lo que sugiere su xG: ${dec1(num(metrics, "goals"))} goles (${pct(num(metrics, "goals_percentile"))}) frente a ${dec1(num(metrics, "xg"))} xG (${pct(num(metrics, "xg_percentile"))}).`;
    case "high_volume_low_quality_shooting":
      return `Alto volumen de tiros (${pct(num(metrics, "shots_percentile"))}) con baja precisión (${pct(num(metrics, "shot_accuracy_percentile"))}).`;
    case "breakout_signal":
      return `Señal de breakout: watchlist ${dec1(num(metrics, "watchlist_score"))}, nivel estable ${dec1(num(metrics, "stable_score"))}, sorpresa ${signed1(num(metrics, "surprise_delta"))}, tendencia ${signed1(num(metrics, "trend_delta"))}.`;
    case "underrated":
      return `Percepción externa por debajo del rendimiento: nivel estable ${dec1(num(metrics, "performance_score"))} vs percepción ${dec1(num(metrics, "perception_score"))} (gap ${signed1(num(metrics, "rating_gap"))}). No es valor de mercado.`;
    case "overrated":
      return `Percepción externa por encima del rendimiento: nivel estable ${dec1(num(metrics, "performance_score"))} vs percepción ${dec1(num(metrics, "perception_score"))} (gap ${signed1(num(metrics, "rating_gap"))}). No es valor de mercado.`;
    case "results_above_process":
      return `Resultados por encima del proceso observado (delta ${signed1(num(metrics, "results_process_delta"))}); score ${dec1(num(metrics, "overall_score"))}.`;
    case "results_below_process":
      return `Resultados por debajo del proceso observado (delta ${signed1(num(metrics, "results_process_delta"))}); score ${dec1(num(metrics, "overall_score"))}.`;
    case "creation_problem":
      return `El problema principal parece estar en la generación de ocasiones (${pct(num(metrics, "chance_generation"))}) más que en la conversión (${pct(num(metrics, "finishing_proxy"))}).`;
    case "defensive_process_weak":
      return `Proceso defensivo débil en esta ventana (${pct(num(metrics, "defense"))}).`;
    case "defensive_process_strong":
      return `Proceso defensivo sólido en esta ventana (${pct(num(metrics, "defense"))}).`;
    case "regression_risk":
      return `Resultados muy por encima del proceso con confianza todavía baja (delta ${signed1(num(metrics, "results_process_delta"))}, ${int(num(metrics, "matches"))} partidos): riesgo de regresión hacia el proceso.`;
    case "sterile_possession":
      return `Alta posesión (${pct(num(metrics, "possession_percentile"))}) con baja generación de ocasiones (${pct(num(metrics, "chance_generation_percentile"))}).`;
    case "few_but_high_quality_chances_allowed":
      return `Permite pocos tiros pero de calidad relativamente alta: tiros ${pct(num(metrics, "shots_total_against_percentile"))}, al arco ${pct(num(metrics, "shots_on_target_against_percentile"))}, xGA ${pct(num(metrics, "xga_percentile"))}.`;
    case "high_volume_low_quality_allowed":
      return `Permite mucho volumen de tiros pero de baja calidad: tiros ${pct(num(metrics, "shots_total_against_percentile"))}, al arco ${pct(num(metrics, "shots_on_target_against_percentile"))}, xGA ${pct(num(metrics, "xga_percentile"))}.`;
    default:
      return `Hallazgo ${code}: ver métricas de soporte.`;
  }
}
