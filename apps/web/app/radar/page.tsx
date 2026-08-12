import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { RadarPlayerCard } from "@/features/radar/radar-player-card";
import { formatDateTime } from "@/lib/player-display";
import { getWorldRadarPage, type WorldRadarFilters } from "@/lib/queries/world-radar";

export const metadata: Metadata = { title: "World Radar" };

const POSITIONS: string[] = ["all", "Attacker", "Midfielder", "Defender", "Goalkeeper"];

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parsePosition(value: string): string {
  return POSITIONS.includes(value) ? value : "all";
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0.4;
}

export default async function RadarPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: WorldRadarFilters = {
    competitionCode: firstValue(params.competition).trim().slice(0, 32),
    position: parsePosition(firstValue(params.position)),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.4"),
    search: firstValue(params.q).trim().slice(0, 80),
  };
  const result = await getWorldRadarPage(filters);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <section className="page-heading">
          <div>
            <p className="eyebrow">WORLD RADAR · V1</p>
            <h1>Producción ofensiva fuera de las core leagues</h1>
          </div>
        </section>
        <DataNotice title="World Radar no disponible" message={result.message} />
      </main>
    );
  }

  const { context, players } = result.data;

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">WORLD RADAR · V1</p>
          <h1>Radar ofensivo/creativo</h1>
          <p>
            World Radar V1 detecta producción ofensiva/creativa dentro de competiciones
            externas. El score es relativo a cada competición y no es una comparación
            directa de nivel entre ligas. No cubre centrales defensivos, laterales
            puramente defensivos, arqueros, scouting completo, calidad de liga, valor de
            mercado ni potencial de transferencia.
          </p>
        </div>
        {context ? (
          <div className="context-card">
            <span>{context.seasonLabel}</span>
            <strong>{context.modelVersion}</strong>
            <small>{formatDateTime(context.calculatedAt)}</small>
          </div>
        ) : null}
      </section>

      {context ? (
        <form className="filters" method="get">
          <label>
            <span>Competición</span>
            <select defaultValue={filters.competitionCode} name="competition">
              <option value="">Todas</option>
              {context.competitions.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name} ({item.country})
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Posición</span>
            <select defaultValue={filters.position} name="position">
              {POSITIONS.map((position) => (
                <option key={position} value={position}>
                  {position === "all" ? "Todas" : position}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Confianza mínima</span>
            <select defaultValue={String(filters.minConfidence)} name="confidence">
              <option value="0">Sin filtro</option>
              <option value="0.25">25%</option>
              <option value="0.4">40%</option>
              <option value="0.6">60%</option>
              <option value="0.75">75%</option>
            </select>
          </label>
          <label className="search-field">
            <span>Jugador / equipo</span>
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
      ) : null}

      {!context ? (
        <DataNotice
          title="Sin snapshots de World Radar"
          message="Ejecutá el workflow manual World Radar (workflow_dispatch) para generar candidatos."
        />
      ) : players.length === 0 ? (
        <DataNotice
          title="Sin candidatos para estos filtros"
          message="Probá bajar la confianza mínima, cambiar la competición o la búsqueda."
        />
      ) : (
        <section className="panel rankings-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">CANDIDATOS</p>
              <h2>Producción ofensiva/creativa observada</h2>
            </div>
            <p>Percentiles calculados dentro de cada competición, no entre competiciones.</p>
          </div>
          <div className="ranking-list">
            {players.map((player, index) => (
              <RadarPlayerCard
                key={`${player.competitionCode}-${player.providerPlayerId}`}
                player={player}
                rank={index + 1}
              />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
