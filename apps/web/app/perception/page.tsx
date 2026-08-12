import type { Metadata } from "next";
import { connection } from "next/server";

import { PerceptionEvidenceCard } from "@/features/perception/evidence-card";
import { DataNotice } from "@/features/players/data-notice";
import { formatDateTime } from "@/lib/player-display";
import {
  getPerceptionPage,
  type PerceptionFilters,
  type PerceptionSourceKind,
} from "@/lib/queries/perception";

export const metadata: Metadata = { title: "Perception Intelligence" };

const KINDS: (PerceptionSourceKind | "all")[] = [
  "all",
  "expert",
  "media",
  "fan",
  "other",
];

const KIND_LABELS: Record<PerceptionSourceKind | "all", string> = {
  all: "Todas",
  expert: "Expertos",
  media: "Medios",
  fan: "Fans",
  other: "Otras",
};

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function parseKind(value: string): PerceptionSourceKind | "all" {
  return KINDS.includes(value as PerceptionSourceKind | "all")
    ? (value as PerceptionSourceKind | "all")
    : "all";
}

export default async function PerceptionPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const params = await searchParams;
  const filters: PerceptionFilters = {
    kind: parseKind(firstValue(params.kind)),
    search: firstValue(params.q).trim().slice(0, 80),
  };
  const result = await getPerceptionPage(filters);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <section className="page-heading">
          <div>
            <p className="eyebrow">PERCEPTION INTELLIGENCE · EVIDENCE V1</p>
            <h1>Evidencia antes que reputación.</h1>
          </div>
        </section>
        <DataNotice
          title="Perception Intelligence no disponible"
          message={result.message}
        />
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">PERCEPTION INTELLIGENCE · EVIDENCE V1</p>
          <h1>Qué se está diciendo, con fuente y contexto.</h1>
          <p>
            Registro auditable de evidencia externa vinculada a jugadores.
            Evidencia, no veredicto: todavía no existe un score de percepción ni
            una etiqueta de sobrevalorado o infravalorado. Eso corresponde al
            siguiente bloque.
          </p>
        </div>
      </section>

      <form className="filters" method="get">
        <label>
          <span>Tipo de fuente</span>
          <select defaultValue={filters.kind} name="kind">
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </label>
        <label className="search-field">
          <span>Buscar evidencia o jugador</span>
          <input
            defaultValue={filters.search}
            name="q"
            placeholder="Ej. Web Smoke Forward"
            type="search"
          />
        </label>
        <button className="button button-primary filter-button" type="submit">
          Aplicar
        </button>
      </form>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SOURCE REGISTRY</p>
            <h2>Cobertura de fuentes</h2>
          </div>
          <p>Los duplicados entre fuentes no inflan el conteo canónico.</p>
        </div>

        {result.data.sources.length === 0 ? (
          <p className="ranking-summary">No hay fuentes activas para este filtro.</p>
        ) : (
          <div className="window-grid">
            {result.data.sources.map((source) => (
              <article className="window-card" key={source.sourceCode}>
                <span>{KIND_LABELS[source.sourceKind]}</span>
                <strong>{source.uniqueEvidenceCount}</strong>
                <small>
                  {source.sourceName}
                  {source.lastPublishedAt
                    ? ` · última ${formatDateTime(source.lastPublishedAt)}`
                    : " · sin evidencia todavía"}
                </small>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel rankings-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PROVENANCE</p>
            <h2>Evidencia reciente</h2>
          </div>
          <p>Solo entradas canónicas; cada tarjeta enlaza al origen.</p>
        </div>

        {result.data.evidence.length === 0 ? (
          <p className="ranking-summary">
            Sin evidencia que coincida con estos filtros.
          </p>
        ) : (
          <div className="ranking-list">
            {result.data.evidence.map((item) => (
              <PerceptionEvidenceCard evidence={item} key={item.evidenceId} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
