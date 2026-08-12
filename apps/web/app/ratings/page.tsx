import type { Metadata } from "next";
import { connection } from "next/server";

import { RatingPlayerCard } from "@/features/rating/rating-player-card";
import { DataNotice } from "@/features/players/data-notice";
import { formatDateTime, ROLE_LABELS } from "@/lib/player-display";
import {
  getRatingsPage,
  type RatingFilters,
  type RatingPlayer,
} from "@/lib/queries/rating-intelligence";
import type { PlayerRole } from "@/lib/queries/player-analytics";

export const metadata: Metadata = { title: "Rating Intelligence" };

const ROLES: (PlayerRole | "all")[] = [
  "all",
  "goalkeeper",
  "defender",
  "midfielder",
  "forward",
];

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseRole(value: string): PlayerRole | "all" {
  return ROLES.includes(value as PlayerRole | "all")
    ? (value as PlayerRole | "all")
    : "all";
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0.5;
}

export default async function RatingsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: RatingFilters = {
    role: parseRole(firstValue(params.role)),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.5"),
    search: firstValue(params.q).trim().slice(0, 80),
  };
  const result = await getRatingsPage(filters);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <section className="page-heading">
          <div>
            <p className="eyebrow">RATING INTELLIGENCE · V1</p>
            <h1>Rendimiento vs percepción</h1>
          </div>
        </section>
        <DataNotice title="Rating Intelligence no disponible" message={result.message} />
      </main>
    );
  }

  const { context, players } = result.data;
  const underrated = players
    .filter((player) => player.ratingSignal === "underrated" && player.ratingGap !== null)
    .sort((a, b) => (b.ratingGap ?? 0) - (a.ratingGap ?? 0))
    .slice(0, 10);
  const overrated = players
    .filter((player) => player.ratingSignal === "overrated" && player.ratingGap !== null)
    .sort((a, b) => (a.ratingGap ?? 0) - (b.ratingGap ?? 0))
    .slice(0, 10);
  const consensus = players
    .filter((player) => player.consensusScore !== null && player.scoredSourceCount >= 2)
    .sort((a, b) => (b.consensusScore ?? 0) - (a.consensusScore ?? 0))
    .slice(0, 10);
  const polarization = players
    .filter((player) => player.polarizationScore !== null && player.scoredSourceCount >= 2)
    .sort((a, b) => (b.polarizationScore ?? 0) - (a.polarizationScore ?? 0))
    .slice(0, 10);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">RATING INTELLIGENCE · V1</p>
          <h1>Lo que rinde vs lo que se dice</h1>
          <p>
            Compara nivel estable con percepción externa suficientemente respaldada.
            No es valor de mercado ni una sentencia sobre el jugador: sin fuentes,
            volumen y confianza suficientes no hay etiqueta.
          </p>
        </div>
        {context ? (
          <div className="context-card">
            <span>{context.scopeKey}</span>
            <strong>{context.modelVersion}</strong>
            <small>{formatDateTime(context.calculatedAt)}</small>
          </div>
        ) : null}
      </section>

      <form className="filters" method="get">
        <label>
          <span>Rol</span>
          <select defaultValue={filters.role} name="role">
            <option value="all">Todos</option>
            {ROLES.filter((role): role is PlayerRole => role !== "all").map((role) => (
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
        <label className="search-field">
          <span>Jugador</span>
          <input
            defaultValue={filters.search}
            name="q"
            placeholder="Buscar por nombre"
            type="search"
          />
        </label>
        <button className="button button-primary filter-button" type="submit">
          Aplicar
        </button>
      </form>

      {!context ? (
        <DataNotice
          title="Sin snapshots de rating"
          message="Calculá rating-v1.0 después de Meta y Perception Intelligence."
        />
      ) : (
        <>
          <RatingSection
            title="Infravalorados"
            subtitle="Nivel estable claramente por encima de una percepción externa suficientemente respaldada."
            players={underrated}
            emphasis="rating"
          />
          <RatingSection
            title="Sobrevalorados"
            subtitle="Percepción externa claramente por encima del nivel estable, con confianza suficiente."
            players={overrated}
            emphasis="rating"
          />
          <RatingSection
            title="Consenso"
            subtitle="Fuerza y acuerdo direccional entre evidencia independiente; no mide rendimiento."
            players={consensus}
            emphasis="consensus"
          />
          <RatingSection
            title="Polarización"
            subtitle="Desacuerdo entre evidencia balanceada por fuente. Una polarización alta bloquea etiquetas forzadas."
            players={polarization}
            emphasis="polarization"
          />
        </>
      )}
    </main>
  );
}

function RatingSection({
  title,
  subtitle,
  players,
  emphasis,
}: {
  title: string;
  subtitle: string;
  players: RatingPlayer[];
  emphasis: "rating" | "consensus" | "polarization";
}) {
  return (
    <section className="panel rankings-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">RATING</p>
          <h2>{title}</h2>
        </div>
        <p>{subtitle}</p>
      </div>
      {players.length === 0 ? (
        <p className="ranking-summary">Sin jugadores con evidencia suficiente para esta señal.</p>
      ) : (
        <div className="ranking-list">
          {players.map((player, index) => (
            <RatingPlayerCard
              emphasis={emphasis}
              key={player.playerId}
              player={player}
              rank={index + 1}
            />
          ))}
        </div>
      )}
    </section>
  );
}
