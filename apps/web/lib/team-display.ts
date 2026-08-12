import type {
  ResultsProcessSignal,
  TeamWindow,
} from "@/lib/queries/team-analytics";

export const TEAM_WINDOW_LABELS: Record<TeamWindow, string> = {
  season: "Performance",
  last_10: "Últimos 10",
  last_5: "Forma · últimos 5",
  last_3: "Últimos 3",
};

export const TEAM_DIMENSION_LABELS: Record<string, string> = {
  attack: "Ataque",
  chance_generation: "Generación de ocasiones",
  finishing_proxy: "Proxy de conversión",
  defense: "Proceso defensivo",
  control: "Proxy de control",
  process: "Proceso",
  results: "Resultados",
};

export const TEAM_METRIC_LABELS: Record<string, string> = {
  goals_for: "Goles a favor / partido",
  goals_against: "Goles en contra / partido",
  goal_difference_per_match: "Diferencia de gol / partido",
  points_per_match: "Puntos por partido",
  shots_total_for: "Tiros a favor / partido",
  shots_on_target_for: "Tiros al arco / partido",
  shots_inside_box_for: "Tiros en el área / partido",
  corners_for: "Corners / partido",
  shots_total_against: "Tiros rivales / partido",
  shots_on_target_against: "Tiros al arco rivales / partido",
  shots_inside_box_against: "Tiros rivales en el área / partido",
  possession_pct: "Posesión",
  pass_accuracy_pct: "Precisión de pase",
  pass_share: "Participación en pases",
  goals_per_shot: "Goles por tiro",
  goals_per_shot_on_target: "Goles por tiro al arco",
};

export const RESULTS_PROCESS_LABELS: Record<ResultsProcessSignal, string> = {
  results_above_process: "Resultados por encima del proceso",
  results_below_process: "Resultados por debajo del proceso",
  results_aligned: "Resultados alineados con el proceso",
};

export const DIAGNOSTIC_LABELS: Record<string, string> = {
  finishing_issue: "Genera suficiente volumen, pero está convirtiendo poco.",
  creation_issue: "El problema principal parece estar en generar ocasiones o volumen.",
  defensive_process_issue: "Está permitiendo demasiado volumen o peligro rival.",
  results_above_process:
    "Los resultados están por encima del proceso observado; puede influir la conversión, el arco, el contexto o la varianza.",
  results_below_process:
    "Los resultados están por debajo del proceso observado; puede influir la conversión, el arco, el contexto o la varianza.",
};

export function diagnosticSignals(value: Record<string, unknown>): string[] {
  const signals = value.signals;
  return Array.isArray(signals) ? signals.filter((item): item is string => typeof item === "string") : [];
}

export function formatTeamMetric(metricName: string, value: number): string {
  if (["possession_pct", "pass_accuracy_pct", "pass_share"].includes(metricName)) {
    return `${value.toFixed(1)}%`;
  }
  if (["goals_per_shot", "goals_per_shot_on_target"].includes(metricName)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
}
