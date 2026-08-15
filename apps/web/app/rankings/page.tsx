import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { PlayerRankingCard } from "@/features/players/player-ranking-card";
import {
  formatDateTime,
  ROLE_LABELS,
  WINDOW_LABELS,
} from "@/lib/player-display";
import { POSITION_FAMILIES, POSITION_FAMILY_LABELS, type PositionFamily } from "@/lib/position-family";
import {
  getRankings,
  type AnalyticsWindow,
  type PlayerRole,
  type RankingsFilters,
} from "@/lib/queries/player-analytics";

export const metadata: Metadata = {
  title: "Rankings",
};

const WINDOWS: AnalyticsWindow[] = ["season", "last_5", "last_3", "last_10"];
const ROLES: PlayerRole[] = ["goalkeeper", "defender", "midfielder", "forward"];

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseWindow(value: string): AnalyticsWindow {
  return WINDOWS.includes(value as AnalyticsWindow) ? (value as AnalyticsWindow) : "season";
}

function parseRole(value: string): PlayerRole | "all" {
  return value === "all" || ROLES.includes(value as PlayerRole)
    ? (value as PlayerRole | "all")
    : "all";
}

function parsePositionFamily(value: string): PositionFamily | "all" {
  return value === "all" || POSITION_FAMILIES.includes(value as PositionFamily)
    ? (value as PositionFamily | "all")
    : "all";
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0.25;
  }
  return Math.min(1, Math.max(0, parsed));
}

export default async function RankingsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;

  const filters: RankingsFilters = {
    window: parseWindow(firstValue(params.window)),
    role: parseRole(firstValue(params.role) || "all"),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.25"),
    search: firstValue(params.q).trim().slice(0, 80),
    limit: 100,
    positionFamily: parsePositionFamily(firstValue(params.position) || "all"),
  };

  const result = await getRankings(filters);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">PLAYER RANKINGS</p>
          <h1>{WINDOW_LABELS[filters.window]}</h1>
          <p>
            Comparación por rol con percentiles, contexto y shrinkage. Filtrá la confianza para
            separar señales interesantes de rankings ya consolidados.
          </p>
        </div>
        {result.status === "ready" && result.data.context ? (
          <div className="context-card">
            <span>{result.data.context.scopeKey}</span>
            <strong>{result.data.context.modelVersion}</strong>
            <small>{formatDateTime(result.data.context.calculatedAt)}</small>
          </div>
        ) : null}
      </section>

      <form className="filters" method="get">
        <label>
          <span>Vista</span>
          <select defaultValue={filters.window} name="window">
            {WINDOWS.map((window) => (
              <option key={window} value={window}>
                {WINDOW_LABELS[window]}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Rol</span>
          <select defaultValue={filters.role} name="role">
            <option value="all">Todos</option>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Confianza mínima</span>
          <select defaultValue={String(filters.minConfidence)} name="confidence">
            <option value="0">Sin filtro</option>
            <option value="0.25">25%</option>
            <option value="0.5">50%</option>
            <option value="0.75">75%</option>
          </select>
        </label>

        <label>
          <span>Familia posicional (beta)</span>
          <select defaultValue={filters.positionFamily} name="position">
            <option value="all">Todas</option>
            {POSITION_FAMILIES.map((family) => (
              <option key={family} value={family}>
                {POSITION_FAMILY_LABELS[family]}
              </option>
            ))}
          </select>
        </label>

        <label className="search-field">
          <span>Jugador</span>
          <input defaultValue={filters.search} name="q" placeholder="Buscar por nombre" type="search" />
        </label>

        <button className="button button-primary filter-button" type="submit">
          Aplicar
        </button>
      </form>

      {result.status !== "ready" ? (
        <DataNotice
          title={result.status === "unconfigured" ? "Base de datos pendiente" : "No pudimos cargar el ranking"}
          message={result.message}
        />
      ) : result.data.context === null ? (
        <DataNotice
          title="Sin rankings todavía"
          message="No hay snapshots de Player Analytics en PostgreSQL para mostrar."
        />
      ) : result.data.players.length === 0 ? (
        <DataNotice
          title="No hay resultados"
          message="Probá bajar la confianza mínima, cambiar de rol o limpiar la búsqueda."
        />
      ) : (
        <section className="panel rankings-panel">
          <div className="ranking-summary">
            <span>{result.data.players.length} jugadores visibles</span>
            <span>
              {filters.role === "all" ? "Todos los roles" : ROLE_LABELS[filters.role]} · confianza ≥{" "}
              {Math.round(filters.minConfidence * 100)}%
              {filters.positionFamily !== "all"
                ? ` · ${POSITION_FAMILY_LABELS[filters.positionFamily]} (beta)`
                : ""}
            </span>
          </div>
          {filters.positionFamily !== "all" ? (
            <p className="ranking-meta">
              Familia posicional en beta: se clasifica desde la última posición observada en
              cancha, puede no coincidir con el rol táctico habitual del jugador.
            </p>
          ) : null}
          <div className="ranking-list">
            {result.data.players.map((player, index) => (
              <PlayerRankingCard
                key={player.playerId}
                player={player}
                positionFamily={player.positionFamily}
                rank={index + 1}
              />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
