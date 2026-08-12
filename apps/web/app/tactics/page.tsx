import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { TacticalTeamCard } from "@/features/tactical/tactical-team-card";
import { formatDateTime } from "@/lib/player-display";
import {
  getTacticalPage,
  type TacticalFilters,
} from "@/lib/queries/tactical-intelligence";

export const metadata: Metadata = { title: "Tactical Intelligence" };

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseConfidence(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0.4;
}

export default async function TacticsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: TacticalFilters = {
    competitionCode: firstValue(params.competition).trim().slice(0, 32),
    minConfidence: parseConfidence(firstValue(params.confidence) || "0.4"),
    search: firstValue(params.q).trim().slice(0, 80),
  };
  const result = await getTacticalPage(filters);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <section className="page-heading">
          <div>
            <p className="eyebrow">TACTICAL INTELLIGENCE · V1</p>
            <h1>Perfiles tácticos</h1>
          </div>
        </section>
        <DataNotice title="Tactical Intelligence no disponible" message={result.message} />
      </main>
    );
  }

  const { contexts, context, teams } = result.data;

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">TACTICAL INTELLIGENCE · V1</p>
          <h1>Cómo produce cada equipo</h1>
          <p>
            Formación nominal observada + proxies de control, volumen ofensivo y
            resistencia defensiva. No inventa presión, altura de bloque, contraataques
            ni movimientos espaciales sin tracking/eventos que los respalden.
          </p>
        </div>
        {context ? (
          <div className="context-card">
            <span>
              {context.competitionName} · {context.seasonLabel}
            </span>
            <strong>{context.modelVersion}</strong>
            <small>{formatDateTime(context.calculatedAt)}</small>
          </div>
        ) : null}
      </section>

      <form className="filters" method="get">
        <label>
          <span>Competición</span>
          <select defaultValue={context?.competitionCode ?? ""} name="competition">
            {contexts.map((item) => (
              <option key={item.scopeKey} value={item.competitionCode}>
                {item.competitionName}
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
          <span>Equipo</span>
          <input
            defaultValue={filters.search}
            name="q"
            placeholder="Buscar equipo"
            type="search"
          />
        </label>
        <button className="button button-primary filter-button" type="submit">
          Aplicar
        </button>
      </form>

      {!context ? (
        <DataNotice
          title="Sin snapshots tácticos"
          message="Calculá tactical-v1.0 después de Team Intelligence."
        />
      ) : teams.length === 0 ? (
        <DataNotice
          title="Sin equipos para estos filtros"
          message="Probá bajar la confianza mínima o cambiar la búsqueda."
        />
      ) : (
        <section className="panel rankings-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">TACTICAL PROFILE</p>
              <h2>Formación y estilo observable</h2>
            </div>
            <p>
              Los scores son proxies relativos a la competición, no coordenadas ni
              etiquetas tácticas absolutas.
            </p>
          </div>
          <div className="ranking-list">
            {teams.map((team, index) => (
              <TacticalTeamCard
                competitionCode={context.competitionCode}
                key={team.teamId}
                rank={index + 1}
                team={team}
              />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
