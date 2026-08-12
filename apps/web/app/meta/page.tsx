import type { Metadata } from "next";
import { connection } from "next/server";

import { MetaPlayerCard } from "@/features/meta/meta-player-card";
import { DataNotice } from "@/features/players/data-notice";
import { formatDateTime, ROLE_LABELS } from "@/lib/player-display";
import { getMetaPage, type MetaFilters, type MetaPlayer } from "@/lib/queries/meta-analytics";
import type { PlayerRole } from "@/lib/queries/player-analytics";

export const metadata: Metadata = { title: "Expectation & Meta" };

const ROLES: (PlayerRole | "all")[] = ["all", "goalkeeper", "defender", "midfielder", "forward"];

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseRole(value: string): PlayerRole | "all" {
  return ROLES.includes(value as PlayerRole | "all") ? (value as PlayerRole | "all") : "all";
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0.25;
}

export default async function MetaPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: MetaFilters = {
    role: parseRole(firstValue(params.role)),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.25"),
    search: firstValue(params.q).trim().slice(0, 80),
  };
  const result = await getMetaPage(filters);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <section className="page-heading">
          <div><p className="eyebrow">EXPECTATION & META · V1</p><h1>Meta Intelligence</h1></div>
        </section>
        <DataNotice title="Meta Intelligence no disponible" message={result.message} />
      </main>
    );
  }

  const { context, players } = result.data;
  const stable = [...players].sort((a, b) => b.stableScore - a.stableScore).slice(0, 10);
  const surprises = players
    .filter((player) => player.surpriseSignal === "surprise" && player.surpriseDelta !== null)
    .sort((a, b) => (b.surpriseDelta ?? 0) - (a.surpriseDelta ?? 0))
    .slice(0, 10);
  const disappointments = players
    .filter((player) => player.surpriseSignal === "disappointment" && player.surpriseDelta !== null)
    .sort((a, b) => (a.surpriseDelta ?? 0) - (b.surpriseDelta ?? 0))
    .slice(0, 10);
  const rising = players
    .filter((player) => player.trendSignal === "rising" && player.trendDelta !== null)
    .sort((a, b) => (b.trendDelta ?? 0) - (a.trendDelta ?? 0))
    .slice(0, 10);
  const watchlist = players
    .filter((player) => player.watchlistSignal !== "none")
    .sort((a, b) => b.watchlistScore - a.watchlistScore)
    .slice(0, 10);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">EXPECTATION & META · V1</p>
          <h1>Qué cambió respecto de su propio nivel</h1>
          <p>
            Expectativa histórica, nivel estable, tendencia y watchlist. La expectativa es un baseline
            de rendimiento previo: no es una predicción ni una valoración de mercado.
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
              <option key={role} value={role}>{ROLE_LABELS[role]}</option>
            ))}
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
          <span>Jugador</span>
          <input defaultValue={filters.search} name="q" placeholder="Buscar por nombre" type="search" />
        </label>
        <button className="button button-primary filter-button" type="submit">Aplicar</button>
      </form>

      {!context ? (
        <DataNotice title="Sin snapshots meta" message="Calculá meta-v1.0 después de Player Analytics." />
      ) : (
        <>
          <MetaSection title="Nivel estable" subtitle="Rendimiento de largo plazo, separado de la Forma." players={stable} emphasis="stable" />
          <MetaSection title="Sorpresas" subtitle="Performance actual claramente por encima del baseline histórico." players={surprises} emphasis="surprise" />
          <MetaSection title="Decepciones" subtitle="Performance actual por debajo de la expectativa histórica, sin inferir causalidad." players={disappointments} emphasis="surprise" />
          <MetaSection title="En subida" subtitle="Gradiente positivo entre ventanas recientes y Performance." players={rising} emphasis="trend" />
          <MetaSection title="Watchlist" subtitle="Calidad estable + señales positivas de sorpresa y tendencia." players={watchlist} emphasis="watchlist" />
        </>
      )}
    </main>
  );
}

function MetaSection({
  title,
  subtitle,
  players,
  emphasis,
}: {
  title: string;
  subtitle: string;
  players: MetaPlayer[];
  emphasis: "stable" | "surprise" | "trend" | "watchlist";
}) {
  const list = players;
  return (
    <section className="panel rankings-panel">
      <div className="section-heading">
        <div><p className="eyebrow">META</p><h2>{title}</h2></div>
        <p>{subtitle}</p>
      </div>
      {list.length === 0 ? (
        <p className="ranking-summary">Sin jugadores con evidencia suficiente para esta señal.</p>
      ) : (
        <div className="ranking-list">
          {list.map((player, index) => (
            <MetaPlayerCard key={player.playerId} player={player} rank={index + 1} emphasis={emphasis} />
          ))}
        </div>
      )}
    </section>
  );
}
