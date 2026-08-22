import type { Metadata } from "next";
import { connection } from "next/server";

import { EmptyState, TeamDirectoryCard, TeamProductCard } from "@/features/product/product-ui";
import { TEAM_DIMENSION_LABELS, WINDOW_LABELS } from "@/lib/product-display";
import { TEAM_RANKING_DIMENSIONS, getProductTeamDirectory, getProductTeamRankings, type TeamRankingDimension } from "@/lib/queries/product-intelligence";
import type { AnalyticsWindow } from "@/lib/queries/player-analytics";

export const metadata: Metadata = { title: "Rankings de equipos V2" };
const WINDOWS: AnalyticsWindow[] = ["season", "last_10", "last_5", "last_3"];
const value = (input: string | string[] | undefined) => Array.isArray(input) ? (input[0] ?? "") : (input ?? "");

export default async function TeamRankingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await connection(); const params = await searchParams;
  const dimension = TEAM_RANKING_DIMENSIONS.includes(value(params.dimension) as TeamRankingDimension) ? value(params.dimension) as TeamRankingDimension : "overall";
  const window = WINDOWS.includes(value(params.window) as AnalyticsWindow) ? value(params.window) as AnalyticsWindow : "season";
  const minConfidence = Math.min(1, Math.max(0.4, Number(value(params.confidence)) || 0.4));
  const filters = { competitionCode: value(params.competition).trim().slice(0, 30), seasonLabel: value(params.season).trim().slice(0, 30), window, minConfidence, search: value(params.q).trim().slice(0, 80), dimension, limit: 100 };
  const result = await getProductTeamRankings(filters); const teams = result.status === "ready" ? result.data.teams : [];
  const directoryResult = teams.length === 0 && result.status === "ready" ? await getProductTeamDirectory(filters.competitionCode, filters.seasonLabel) : null;
  const directoryTeams = directoryResult?.status === "ready" ? directoryResult.data.teams : [];
  return <main className="page-shell"><section className="page-heading"><div><p className="eyebrow">TEAM EXPLORER · V2</p><h1>{TEAM_DIMENSION_LABELS[dimension]}</h1><p>Rankings de equipo con evidencia lista en la dimensión elegida. Una dimensión ausente nunca se interpreta como cero.</p></div></section>
    <form className="filters product-filters" method="get"><label><span>Dimensión</span><select defaultValue={dimension} name="dimension">{TEAM_RANKING_DIMENSIONS.map((item) => <option key={item} value={item}>{TEAM_DIMENSION_LABELS[item]}</option>)}</select></label><label><span>Ventana</span><select defaultValue={window} name="window">{WINDOWS.map((item) => <option key={item} value={item}>{WINDOW_LABELS[item]}</option>)}</select></label><label><span>Confianza</span><select defaultValue={String(minConfidence)} name="confidence"><option value="0.4">40%</option><option value="0.5">50%</option><option value="0.75">75%</option></select></label><label><span>Competición</span><input defaultValue={filters.competitionCode} name="competition" placeholder="ENG_PL" /></label><label><span>Temporada</span><input defaultValue={filters.seasonLabel} name="season" placeholder="2025/26" /></label><label className="search-field"><span>Equipo</span><input defaultValue={filters.search} name="q" type="search" /></label><button className="button button-primary filter-button" type="submit">Aplicar</button></form>
    {teams.length ? (
      <section className="panel"><div className="ranking-summary"><span>{teams.length} equipos elegibles</span><span>{WINDOW_LABELS[window]}</span></div>{teams.map((team, index) => <TeamProductCard key={team.teamId} team={team} rank={index + 1} />)}</section>
    ) : directoryTeams.length ? (
      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">ANÁLISIS DISPONIBLE · RANKING NO DISPONIBLE</p><h2>Equipos analizados</h2></div></div>
        <p className="ranking-summary">No hay evidencia suficiente para ordenar los equipos de forma defendible, pero sí podés explorar el análisis disponible de cada uno.</p>
        <div className="signal-list">{directoryTeams.map((team) => <TeamDirectoryCard key={team.teamId} team={team} />)}</div>
      </section>
    ) : (
      <EmptyState title="Ranking de equipos no disponible" missing={result.status === "ready" ? "Ningún equipo real V2 tiene evidencia lista para esta dimensión y filtros." : result.message} unlock="Se habilita cuando la dimensión alcanza muestra, cobertura y confianza publicables." />
    )}
  </main>;
}
