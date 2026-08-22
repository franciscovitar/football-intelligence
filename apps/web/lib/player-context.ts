export interface PlayerContextChoice {
  scopeKey: string;
  competitionCode: string;
  competitionName: string;
  seasonLabel: string;
  isHistorical: boolean;
}

export interface ParsedCompetitionScope {
  competitionCode: string;
  seasonLabel: string;
}

export function parseCompetitionScopeKey(scopeKey: string): ParsedCompetitionScope | null {
  const parts = scopeKey.trim().split(":");
  if (parts.length !== 3 || parts[0] !== "competition") return null;
  const competitionCode = parts[1]?.trim() ?? "";
  const seasonLabel = parts[2]?.trim() ?? "";
  if (!competitionCode || !seasonLabel) return null;
  return { competitionCode, seasonLabel };
}

export function selectPlayerContext<T extends { scopeKey: string }>(
  contexts: readonly T[],
  requestedScopeKey: string,
): T | null {
  const requested = requestedScopeKey.trim();
  if (!requested) return contexts[0] ?? null;
  return contexts.find((context) => context.scopeKey === requested) ?? null;
}
