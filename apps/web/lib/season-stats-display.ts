import type { PlayerSeasonStats } from "@/lib/queries/season-stats";

export const SEASON_STAT_LABELS: Record<string, string> = {
  minutes: "Minutos",
  starts: "Titularidades",
  appearances: "Apariciones",
  goals: "Goles",
  assists: "Asistencias",
  cleanSheets: "Vallas invictas",
  goalsConceded: "Goles recibidos",
  ownGoals: "Goles en contra",
  penaltiesSaved: "Penales atajados",
  penaltiesMissed: "Penales errados",
  yellowCards: "Amarillas",
  redCards: "Rojas",
  saves: "Atajadas",
  bonus: "Puntos bonus",
  bps: "BPS",
  influence: "Influence",
  creativity: "Creativity",
  threat: "Threat",
  ictIndex: "ICT Index",
  tackles: "Entradas",
  recoveries: "Recuperaciones",
  clearancesBlocksInterceptions: "Despejes + bloqueos + intercepciones",
  defensiveContribution: "Contribución defensiva",
  expectedGoals: "xG",
  expectedAssists: "xA",
  expectedGoalInvolvements: "xGI",
  expectedGoalsConceded: "xGC",
};

export type SeasonStatNumericKey = Exclude<
  keyof PlayerSeasonStats,
  "seasonLabel" | "source" | "sourceUrl" | "retrievedAt" | "semanticVersion"
>;

// Fixed, deliberate order -- never `Object.entries` insertion order, so the
// panel reads goals/assists/minutes first regardless of column order in the
// underlying table.
export const SEASON_STAT_ORDER: SeasonStatNumericKey[] = [
  "goals",
  "assists",
  "expectedGoals",
  "expectedAssists",
  "expectedGoalInvolvements",
  "minutes",
  "starts",
  "appearances",
  "ictIndex",
  "influence",
  "creativity",
  "threat",
  "tackles",
  "recoveries",
  "clearancesBlocksInterceptions",
  "defensiveContribution",
  "cleanSheets",
  "goalsConceded",
  "expectedGoalsConceded",
  "saves",
  "penaltiesSaved",
  "penaltiesMissed",
  "ownGoals",
  "yellowCards",
  "redCards",
  "bonus",
  "bps",
];

export function formatSeasonStat(value: number | null): string {
  if (value === null) return "No disponible";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
