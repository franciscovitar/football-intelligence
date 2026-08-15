import type { Metadata } from "next";
import { connection } from "next/server";

import { EmptyState, PlayerProductCard } from "@/features/product/product-ui";
import { PLAYER_DIMENSION_LABELS, WINDOW_LABELS } from "@/lib/product-display";
import { POSITION_FAMILIES, POSITION_FAMILY_LABELS, type PositionFamily } from "@/lib/position-family";
import { PLAYER_RANKING_DIMENSIONS, getProductPlayerRankings, type PlayerRankingDimension } from "@/lib/queries/product-intelligence";
import type { AnalyticsWindow } from "@/lib/queries/player-analytics";

export const metadata: Metadata = { title: "Rankings de jugadores V2" };
const WINDOWS: AnalyticsWindow[] = ["season", "last_10", "last_5", "last_3"];
const value = (input: string | string[] | undefined) => Array.isArray(input) ? (input[0] ?? "") : (input ?? "");
const bounded = (input: string, fallback: number, max = 1) => { const parsed = Number(input); return Number.isFinite(parsed) ? Math.min(max, Math.max(0, parsed)) : fallback; };

export default async function RankingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await connection();
  const params = await searchParams;
  const window = WINDOWS.includes(value(params.window) as AnalyticsWindow) ? value(params.window) as AnalyticsWindow : "season";
  const dimension = PLAYER_RANKING_DIMENSIONS.includes(value(params.dimension) as PlayerRankingDimension) ? value(params.dimension) as PlayerRankingDimension : "overall";
  const position: PositionFamily | "all" = POSITION_FAMILIES.includes(value(params.position) as PositionFamily) ? value(params.position) as PositionFamily : "all";
  const minMinutes = Math.round(bounded(value(params.minutes), window === "season" ? 450 : window === "last_10" ? 270 : window === "last_5" ? 180 : 90, 10000));
  const minConfidence = bounded(value(params.confidence), 0.4);
  const filters = { competitionCode: value(params.competition).trim().slice(0, 30), seasonLabel: value(params.season).trim().slice(0, 30), window, positionFamily: position, minMinutes, minConfidence, search: value(params.q).trim().slice(0, 80), dimension, limit: 100 };
  const result = await getProductPlayerRankings(filters);
  const players = result.status === "ready" ? result.data.players : [];

  return <main className="page-shell">
    <section className="page-heading"><div><p className="eyebrow">PLAYER EXPLORER · V2</p><h1>{PLAYER_DIMENSION_LABELS[dimension]}</h1><p>Solo aparecen jugadores reales con evidencia lista para esta dimensión. Muestra y confianza se filtran antes de ordenar.</p></div></section>
    <form className="filters product-filters" method="get">
      <label><span>Dimensión</span><select defaultValue={dimension} name="dimension">{PLAYER_RANKING_DIMENSIONS.map((item) => <option key={item} value={item}>{PLAYER_DIMENSION_LABELS[item]}</option>)}</select></label>
      <label><span>Ventana</span><select defaultValue={window} name="window">{WINDOWS.map((item) => <option key={item} value={item}>{WINDOW_LABELS[item]}</option>)}</select></label>
      <label><span>Posición</span><select defaultValue={position} name="position"><option value="all">Todas</option>{POSITION_FAMILIES.map((item) => <option key={item} value={item}>{POSITION_FAMILY_LABELS[item]}</option>)}</select></label>
      <label><span>Minutos mínimos</span><input defaultValue={minMinutes} min="0" name="minutes" type="number" /></label>
      <label><span>Confianza mínima</span><select defaultValue={String(minConfidence)} name="confidence"><option value="0.4">40%</option><option value="0.5">50%</option><option value="0.75">75%</option></select></label>
      <label><span>Competición</span><input defaultValue={filters.competitionCode} name="competition" placeholder="ENG_PL" /></label>
      <label><span>Temporada</span><input defaultValue={filters.seasonLabel} name="season" placeholder="2025/26" /></label>
      <label className="search-field"><span>Jugador</span><input defaultValue={filters.search} name="q" placeholder="Buscar por nombre" type="search" /></label>
      <button className="button button-primary filter-button" type="submit">Aplicar</button>
    </form>
    {result.status !== "ready" ? <EmptyState title="No pudimos leer el ranking" missing={result.message} unlock="Revisá la conexión del snapshot real V2." /> : players.length === 0 ? <EmptyState title="Insufficient real data for this ranking" missing="Ningún jugador cumple simultáneamente la dimensión, muestra y confianza seleccionadas." unlock="Probá otra dimensión o ventana; los datos test/smoke nunca se usan como reemplazo." /> : <>
      <section className="top-four-grid">{players.slice(0, 4).map((player, index) => <PlayerProductCard key={player.playerId} player={player} rank={index + 1} prominent />)}</section>
      {players.length > 4 ? <section className="panel"><div className="ranking-summary"><span>{players.length} jugadores elegibles</span><span>{WINDOW_LABELS[window]} · ≥ {minMinutes} min · ≥ {Math.round(Math.max(0.4, minConfidence) * 100)}% conf.</span></div>{players.slice(4).map((player, index) => <PlayerProductCard key={player.playerId} player={player} rank={index + 5} />)}</section> : null}
    </>}
  </main>;
}
