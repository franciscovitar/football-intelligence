import type { Metadata } from "next";
import { connection } from "next/server";

import { EmptyState, PlayerDirectoryCard, PlayerProductCard } from "@/features/product/product-ui";
import { selectPlayerContext } from "@/lib/player-context";
import { PLAYER_DIMENSION_LABELS, WINDOW_LABELS } from "@/lib/product-display";
import { POSITION_FAMILIES, POSITION_FAMILY_LABELS, type PositionFamily } from "@/lib/position-family";
import { PLAYER_RANKING_DIMENSIONS, type PlayerRankingDimension } from "@/lib/queries/product-intelligence";
import {
  getScopedPlayerContexts,
  getScopedPlayerDirectory,
  getScopedPlayerRankings,
} from "@/lib/queries/scoped-player-intelligence";
import type { AnalyticsWindow } from "@/lib/queries/player-analytics";

export const metadata: Metadata = { title: "Jugadores V2" };
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
  const search = value(params.q).trim().slice(0, 80);
  const requestedContext = value(params.context).trim().slice(0, 120);

  const contextsResult = await getScopedPlayerContexts();
  const contexts = contextsResult.status === "ready" ? contextsResult.data : [];
  const selectedContext = selectPlayerContext(contexts, requestedContext);
  const contextScopeKey = selectedContext?.scopeKey ?? (requestedContext || "invalid");

  const [rankingResult, directoryResult] = await Promise.all([
    getScopedPlayerRankings({
      contextScopeKey,
      window,
      positionFamily: position,
      minMinutes,
      minConfidence,
      search,
      dimension,
      limit: 100,
    }),
    getScopedPlayerDirectory({
      contextScopeKey,
      positionFamily: position,
      minMinutes,
      search,
      limit: 600,
    }),
  ]);
  const players = rankingResult.status === "ready" ? rankingResult.data.players : [];
  const directory = directoryResult.status === "ready" ? directoryResult.data.players : [];

  return <main className="page-shell">
    <section className="page-heading"><div><p className="eyebrow">PLAYER EXPLORER · V2 {selectedContext?.isHistorical ? "· HISTÓRICO" : ""}</p><h1>{players.length ? PLAYER_DIMENSION_LABELS[dimension] : "Jugadores analizados"}</h1><p>{selectedContext ? `${selectedContext.competitionName} · ${selectedContext.seasonLabel}. ` : ""}Los rankings solo aparecen cuando la dimensión, muestra y confianza superan todos los controles; una ficha real puede existir aunque el ranking siga cerrado.</p></div></section>
    <form className="filters product-filters" method="get">
      <label><span>Contexto</span><select defaultValue={selectedContext?.scopeKey ?? ""} name="context" required><option disabled value="">Elegir contexto</option>{contexts.map((item) => <option key={item.scopeKey} value={item.scopeKey}>{item.competitionName} · {item.seasonLabel}{item.isHistorical ? " · Histórico" : ""}</option>)}</select></label>
      <label><span>Dimensión</span><select defaultValue={dimension} name="dimension">{PLAYER_RANKING_DIMENSIONS.map((item) => <option key={item} value={item}>{PLAYER_DIMENSION_LABELS[item]}</option>)}</select></label>
      <label><span>Ventana</span><select defaultValue={window} name="window">{WINDOWS.map((item) => <option key={item} value={item}>{WINDOW_LABELS[item]}</option>)}</select></label>
      <label><span>Posición</span><select defaultValue={position} name="position"><option value="all">Todas</option>{POSITION_FAMILIES.map((item) => <option key={item} value={item}>{POSITION_FAMILY_LABELS[item]}</option>)}</select></label>
      <label><span>Minutos mínimos</span><input defaultValue={minMinutes} min="0" name="minutes" type="number" /></label>
      <label><span>Confianza mínima del ranking</span><select defaultValue={String(minConfidence)} name="confidence"><option value="0.4">40%</option><option value="0.5">50%</option><option value="0.75">75%</option></select></label>
      <label className="search-field"><span>Jugador</span><input defaultValue={search} name="q" placeholder="Buscar por nombre" type="search" /></label>
      <button className="button button-primary filter-button" type="submit">Aplicar</button>
    </form>
    {contextsResult.status !== "ready" ? <EmptyState title="No pudimos leer los contextos de jugadores" missing={contextsResult.message} unlock="Revisá la conexión del snapshot real V2." /> : contexts.length === 0 ? <EmptyState title="Todavía no hay temporadas de jugadores publicadas" missing="No existe un contexto explícito Player V2 en la base de producto." unlock="Cargá y calculá una temporada real antes de exponer jugadores." /> : !selectedContext ? <EmptyState title="Contexto de jugadores no válido" missing="La temporada solicitada no coincide con un contexto Player V2 publicado." unlock="Elegí uno de los contextos disponibles." /> : rankingResult.status !== "ready" || directoryResult.status !== "ready" ? <EmptyState title="No pudimos leer la inteligencia de jugadores" missing={rankingResult.status !== "ready" ? rankingResult.message : directoryResult.status !== "ready" ? directoryResult.message : "Error desconocido"} unlock="Revisá el estado del snapshot real V2." /> : players.length ? <>
      <section className="top-four-grid">{players.slice(0, 4).map((player, index) => <PlayerProductCard contextScopeKey={selectedContext.scopeKey} key={player.playerId} player={player} rank={index + 1} prominent />)}</section>
      {players.length > 4 ? <section className="panel"><div className="ranking-summary"><span>{players.length} jugadores elegibles</span><span>{WINDOW_LABELS[window]} · ≥ {minMinutes} min · ≥ {Math.round(Math.max(0.4, minConfidence) * 100)}% conf.</span></div>{players.slice(4).map((player, index) => <PlayerProductCard contextScopeKey={selectedContext.scopeKey} key={player.playerId} player={player} rank={index + 5} />)}</section> : null}
    </> : directory.length ? <section className="panel"><div className="section-heading"><div><p className="eyebrow">ANÁLISIS DISPONIBLE · RANKING NO DISPONIBLE</p><h2>Jugadores analizados</h2></div><span>{directory.length} con los filtros actuales</span></div><p>No hay evidencia suficiente para ordenar a los jugadores de forma defendible, pero sí podés explorar el análisis real disponible de cada uno.</p><div className="signal-list">{directory.map((player) => <PlayerDirectoryCard key={player.playerId} player={player} />)}</div></section> : <EmptyState title="Sin jugadores para estos filtros" missing="El contexto existe, pero ningún jugador cumple los minutos, posición y búsqueda seleccionados." unlock="Probá bajar los minutos mínimos o quitar filtros; nunca bajamos los gates científicos del ranking." />}
  </main>;
}
