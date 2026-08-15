/**
 * Web-side mirror of `analytics/.../position_profiles/config.py`'s
 * `FINE_POSITION_ALIASES`. Deliberately small and explicit -- an
 * unrecognized `listed_position` token is never guessed, it just classifies
 * as `null` ("beta"/uncategorized) rather than a fake broad-role fallback.
 * Kept as a plain object literal (no network round-trip to the Python
 * engine) since `listed_position` is already real, queried data
 * (`football.player_appearances.listed_position`), not invented.
 */
export type PositionFamily =
  | "goalkeeper"
  | "centre_back"
  | "fullback_wingback"
  | "defensive_midfielder"
  | "central_midfielder"
  | "attacking_midfielder"
  | "winger"
  | "forward";

const FINE_POSITION_ALIASES: Record<string, PositionFamily> = {
  GK: "goalkeeper",
  CB: "centre_back",
  RB: "fullback_wingback",
  LB: "fullback_wingback",
  RWB: "fullback_wingback",
  LWB: "fullback_wingback",
  CDM: "defensive_midfielder",
  DM: "defensive_midfielder",
  CM: "central_midfielder",
  CAM: "attacking_midfielder",
  AM: "attacking_midfielder",
  RW: "winger",
  LW: "winger",
  RM: "winger",
  LM: "winger",
  ST: "forward",
  CF: "forward",
  FW: "forward",
};

export const POSITION_FAMILIES: PositionFamily[] = [
  "goalkeeper",
  "centre_back",
  "fullback_wingback",
  "defensive_midfielder",
  "central_midfielder",
  "attacking_midfielder",
  "winger",
  "forward",
];

export const POSITION_FAMILY_LABELS: Record<PositionFamily, string> = {
  goalkeeper: "Arquero",
  centre_back: "Central",
  fullback_wingback: "Lateral / carrilero",
  defensive_midfielder: "Volante defensivo",
  central_midfielder: "Volante central",
  attacking_midfielder: "Enganche / mediapunta",
  winger: "Extremo",
  forward: "Delantero centro",
};

export function classifyPositionFamily(listedPosition: string | null): PositionFamily | null {
  if (!listedPosition) return null;
  const token = listedPosition.trim().toUpperCase();
  return FINE_POSITION_ALIASES[token] ?? null;
}
