import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { TeamRankingCard } from "@/features/teams/team-ranking-card";
import { formatDateTime } from "@/lib/player-display";
import {
  getTeamRankings,
  type TeamRankingsFilters,
  type TeamWindow,
} from "@/lib/queries/team-analytics";
import { TEAM_WINDOW_LABELS } from "@/lib/team-display";

export const metadata: Metadata = { title: "Team Intelligence" };
const WINDOWS: TeamWindow[] = ["season", "last_5", "last_3", "last_10"];

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseWindow(value: string): TeamWindow {
  return WINDOWS.includes(value as TeamWindow) ? (value as TeamWindow) : "season";
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0.25;
}

export default async function TeamsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: TeamRankingsFilters = {
    competitionCode: firstValue(params.competition),
    window: parseWindow(firstValue(params.window)),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.25"),
    search: firstValue(params.q).trim().slice(0, 80),
    limit: 100,
  };
  const result = await getTeamRankings(filters);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">TEAM INTELLIGENCE · V1</p>
          <h1>{TEAM_WINDOW_LABELS[filters.window]}</h1>
          <p>
            Proceso, resultados, forma y Elo dentro de cada competición. No mezclamos ligas desconectadas ni llamamos xG a métricas de volumen.
          </p>
        </div>
        {result.status === "ready" && result.data.context ? (
          <div className="context-card">
            <span>{result.data.context.competitionName} · {result.data.context.seasonLabel}</span>
            <strong>{result.data.context.modelVersion}</strong>
            <small>{formatDateTime(result.data.context.calculatedAt)}</small>
          </div>
        ) : null}
      </section>

      <form className="filters" method="get">
        <label>
          <span>Competición</span>
          <select defaultValue={result.status === "ready" ? (result.data.context?.competitionCode ?? "") : filters.competitionCode} name="competition">
            {result.status === "ready"
              ? result.data.contexts.map((context) => (
                  <option key={context.scopeKey} value={context.competitionCode}>
                    {context.competitionName} · {context.seasonLabel}
                  </option>
                ))
              : null}
          </select>
        </label>
        <label>
          <span>Ventana</span>
          <select defaultValue={filters.window} name="window">
            {WINDOWS.map((window) => <option key={window} value={window}>{TEAM_WINDOW_LABELS[window]}</option>)}
          </select>
        </label>
        <label>
          <span>Confianza mínima</span>
          <select defaultValue={String(filters.minConfidence)} name="confidence">
            <option value="0">Sin filtro</option><option value="0.25">25%</option>
            <option value="0.5">50%</option><option value="0.75">75%</option>
          </select>
        </label>
        <label className="search-field">
          <span>Equipo</span>
          <input defaultValue={filters.search} name="q" placeholder="Buscar por nombre" type="search" />
        </label>
        <button className="button button-primary filter-button" type="submit">Aplicar</button>
      </form>

      {result.status !== "ready" ? (
        <DataNotice title={result.status === "unconfigured" ? "Base de datos pendiente" : "Team Intelligence no disponible"} message={result.message} />
      ) : result.data.context === null ? (
        <DataNotice title="Sin snapshots de equipos" message="Calculá team-v1.0 para una competición y temporada." />
      ) : result.data.teams.length === 0 ? (
        <DataNotice title="No hay resultados" message="Probá bajar la confianza o limpiar la búsqueda." />
      ) : (
        <section className="panel rankings-panel">
          <div className="ranking-summary">
            <span>{result.data.teams.length} equipos · {result.data.context.competitionName}</span>
            <span>La confianza es independiente del score.</span>
          </div>
          <div className="ranking-list">
            {result.data.teams.map((team, index) => (
              <TeamRankingCard key={team.teamId} team={team} rank={index + 1} competitionCode={result.data.context?.competitionCode ?? ""} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
