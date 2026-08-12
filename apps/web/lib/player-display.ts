import type { AnalyticsWindow, PlayerRole } from "@/lib/queries/player-analytics";

export const ROLE_LABELS: Record<PlayerRole, string> = {
  goalkeeper: "Arqueros",
  defender: "Defensores",
  midfielder: "Mediocampistas",
  forward: "Delanteros",
};

export const ROLE_LABELS_SINGULAR: Record<PlayerRole, string> = {
  goalkeeper: "Arquero",
  defender: "Defensor",
  midfielder: "Mediocampista",
  forward: "Delantero",
};

export const WINDOW_LABELS: Record<AnalyticsWindow, string> = {
  season: "Performance",
  last_10: "Últimos 10",
  last_5: "Forma · últimos 5",
  last_3: "Últimos 3",
};

export const METRIC_LABELS: Record<string, string> = {
  goals: "Goles",
  assists: "Asistencias",
  shots_total: "Tiros",
  shots_on_target: "Tiros al arco",
  passes_total: "Pases totales",
  key_passes: "Pases clave",
  tackles: "Entradas",
  blocks: "Bloqueos",
  interceptions: "Intercepciones",
  dribbles_successful: "Regates exitosos",
  duels_won: "Duelos ganados",
  fouls_drawn: "Faltas recibidas",
  fouls_committed: "Faltas cometidas",
  saves: "Atajadas",
};

export const DIMENSION_LABELS: Record<string, string> = {
  scoring: "Definición",
  creation: "Creación",
  carrying: "Conducción",
  defending: "Defensa",
  goalkeeping: "Arco",
};

export function formatScore(value: number): string {
  return value.toFixed(1);
}

export function formatPer90(value: number): string {
  if (Math.abs(value) >= 10) {
    return value.toFixed(1);
  }
  return value.toFixed(2);
}

export function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Argentina/Cordoba",
  }).format(date);
}
