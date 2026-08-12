export const SURPRISE_LABELS: Record<string, string> = {
  surprise: "Sorpresa positiva",
  disappointment: "Por debajo de la expectativa histórica",
  aligned: "En línea con la expectativa",
  insufficient_history: "Sin historia suficiente",
  insufficient_evidence: "Evidencia insuficiente",
};

export const TREND_LABELS: Record<string, string> = {
  rising: "En subida",
  falling: "En baja",
  stable: "Tendencia estable",
  insufficient_data: "Sin ventanas suficientes",
  insufficient_evidence: "Evidencia insuficiente",
};

export const WATCHLIST_LABELS: Record<string, string> = {
  breakout: "Breakout",
  outperforming: "Superando expectativa",
  rising: "En subida",
  monitor: "Seguir",
  none: "Sin señal",
};

export function formatSigned(value: number | null): string {
  if (value === null) return "—";
  const rounded = value.toFixed(1);
  return value > 0 ? `+${rounded}` : rounded;
}
