import type {
  PlayerRankingDimension,
  ProductMetric,
  TeamRankingDimension,
} from "@/lib/queries/product-intelligence";
import type { ScoreEvidenceState } from "@/lib/queries/player-analytics";

export const PLAYER_DIMENSION_LABELS: Record<PlayerRankingDimension, string> = {
  overall: "Overall",
  performance: "Performance",
  underlying_performance: "Rendimiento subyacente",
  finishing: "Definición",
  shot_generation: "Generación de remates",
  creation: "Creación",
  progression: "Progresión",
  passing: "Pase",
  one_v_one: "1 contra 1",
  defence: "Defensa",
  ball_winning: "Recuperación",
  aerial: "Juego aéreo",
  goalkeeping: "Arco",
};

export const TEAM_DIMENSION_LABELS: Record<TeamRankingDimension, string> = {
  overall: "Overall",
  attack: "Ataque",
  defence: "Defensa",
  creation: "Creación",
  finishing: "Definición",
  chance_quality: "Calidad de ocasiones",
  shot_generation: "Generación de remates",
  control: "Control territorial",
  progression: "Progresión",
  penetration: "Penetración",
  build_up: "Salida",
  pressing: "Presión",
  offensive_transition: "Transición ofensiva",
  defensive_transition: "Transición defensiva",
  set_pieces: "Pelota parada",
};

export const WINDOW_LABELS = {
  season: "Temporada",
  last_10: "Últimos 10",
  last_5: "Últimos 5",
  last_3: "Últimos 3",
} as const;

export const EVIDENCE_LABELS: Record<ScoreEvidenceState, string> = {
  ready: "Evidencia lista",
  partial: "Evidencia parcial",
  insufficient_data: "Datos insuficientes",
};

export function formatScore(value: number | null): string {
  return value === null ? "—" : Math.round(value).toString();
}

export function formatNumber(value: number | null, unit = ""): string {
  if (value === null) return "—";
  const formatted = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(value);
  return unit === "percentage" || unit === "percent" ? `${formatted}%` : formatted;
}

export function humanMetric(metric: string): string {
  return metric
    .replaceAll("_pct", " %")
    .replaceAll("_per_90", " /90")
    .replaceAll("_", " ")
    .replace(/^./, (character) => character.toUpperCase());
}

export type MetricCategory =
  | "Output"
  | "Shooting"
  | "Creation"
  | "Passing"
  | "Progression"
  | "1v1"
  | "Possession"
  | "Defending"
  | "Duels"
  | "Goalkeeping"
  | "Context";

export function metricCategory(metric: ProductMetric): MetricCategory {
  const name = metric.metricName;
  if (/save|goal_prevent|post_shot|keeper|cross_stop/.test(name)) return "Goalkeeping";
  if (/duel|aerial/.test(name)) return "Duels";
  if (/tackle|interception|clearance|block|pressure|ball_recover/.test(name)) return "Defending";
  if (/carry|dribble|take_on|one_v_one/.test(name)) return "1v1";
  if (/progress|final_third|penalty_area|deep_completion/.test(name)) return "Progression";
  if (/pass|cross|through_ball/.test(name)) return "Passing";
  if (/assist|chance|key_pass|x?a\b/.test(name)) return "Creation";
  if (/shot|xg|conversion|finishing/.test(name)) return "Shooting";
  if (/goal|output/.test(name)) return "Output";
  if (/possession|touch|turnover|dispossess/.test(name)) return "Possession";
  return "Context";
}

export function stateExplanation(state: ScoreEvidenceState, missing: string[] = []): string {
  const evidence = missing.slice(0, 3).map(humanMetric).join(", ");
  if (state === "partial") {
    return evidence
      ? `Hay una señal orientativa, pero faltan ${evidence}. Se habilita al completar esa evidencia.`
      : "Hay evidencia útil, pero todavía no alcanza para una conclusión completa ni para un ranking.";
  }
  if (state === "insufficient_data") {
    return evidence
      ? `Faltan ${evidence}. Sin esas métricas el modelo no publica un score.`
      : "La muestra o la cobertura no alcanzan. Más minutos y métricas comparables habilitarían el score.";
  }
  return "La muestra, la cobertura y la confianza superan los controles de publicación.";
}
