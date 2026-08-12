export const RADAR_REASON_LABELS: Record<string, string> = {
  top_scorer_feed: "Top scorer feed",
  top_assist_feed: "Top assist feed",
  elite_goals_per90: "Gol/90 de élite (competición)",
  elite_creation_per90: "Creación/90 de élite (competición)",
};

export const RADAR_METRIC_LABELS: Record<string, string> = {
  goals_per90: "Goles/90",
  assists_per90: "Asistencias/90",
  shots_on_target_per90: "Tiros a puerta/90",
  key_passes_per90: "Pases clave/90",
  successful_dribbles_per90: "Regates exitosos/90",
};

export function formatMetric(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(2);
}
