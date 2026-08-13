import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { formatDateTime } from "@/lib/player-display";
import { getDataMeshHealth } from "@/lib/queries/data-mesh";

export const metadata: Metadata = { title: "Fuentes de datos" };

const SOURCE_TYPE_LABELS: Record<string, string> = {
  objective_structured: "Estructurada objetiva",
  objective_official: "Oficial objetiva",
  objective_web: "Web objetiva",
  qualitative_expert: "Cualitativa (experta)",
  qualitative_fan: "Cualitativa (hinchada)",
};

export default async function SourcesPage() {
  await connection();
  const result = await getDataMeshHealth();

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">DATA TRANSPARENCY · V0</p>
          <h1>Fuentes de datos</h1>
          <p>
            Estado real de la malla multi-fuente (Block 13 PoC): qué fuentes están activas,
            qué observan, dónde coinciden y dónde entran en conflicto. Estos datos de
            reconciliación todavía NO alimentan las tablas canónicas de fútbol ni las páginas
            de Player/Team/Rating.
          </p>
        </div>
      </section>

      {result.status !== "ready" ? (
        <DataNotice title="Fuentes de datos no disponibles" message={result.message} />
      ) : (
        <>
          <section className="context-strip">
            <div>
              <span>Observaciones totales</span>
              <strong>{result.data.totalObservations}</strong>
            </div>
            <div>
              <span>Decisiones de reconciliación</span>
              <strong>{result.data.totalDecisions}</strong>
            </div>
            <div>
              <span>Última reconciliación</span>
              <strong>
                {result.data.reconciliation.lastCalculatedAt
                  ? formatDateTime(result.data.reconciliation.lastCalculatedAt)
                  : "—"}
              </strong>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">FUENTES ACTIVAS</p>
                <h2>Proveedores registrados</h2>
              </div>
              <p>Cada fuente conserva su propia procedencia; nunca se sobrescribe en silencio.</p>
            </div>
            {result.data.sources.length === 0 ? (
              <p className="ranking-summary">Sin proveedores registrados todavía.</p>
            ) : (
              <div className="lab-table-wrap">
                <table className="lab-table">
                  <thead>
                    <tr>
                      <th>Fuente</th>
                      <th>Estado</th>
                      <th>Tipo(s)</th>
                      <th>Observaciones</th>
                      <th>Última observación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.sources.map((source) => (
                      <tr key={source.code}>
                        <td>
                          {source.displayName} ({source.code})
                        </td>
                        <td>{source.isActive ? "Activa" : "Inactiva"}</td>
                        <td>
                          {source.sourceTypes.length === 0
                            ? "—"
                            : source.sourceTypes
                                .map((type) => SOURCE_TYPE_LABELS[type] ?? type)
                                .join(", ")}
                        </td>
                        <td>{source.observationCount}</td>
                        <td>
                          {source.lastObservedAt ? formatDateTime(source.lastObservedAt) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">RECONCILIACIÓN</p>
                <h2>Coincidencias, conflictos y evidencia única</h2>
              </div>
              <p>
                Un valor en conflicto nunca se promedia ni se sobrescribe en silencio: queda
                marcado como conflicto con la evidencia de cada fuente.
              </p>
            </div>
            <div className="lab-card-grid">
              <article className="lab-stat">
                <span>Coincidencias (agreed)</span>
                <strong>{result.data.reconciliation.agreedCount}</strong>
                <small>≥2 fuentes independientes de acuerdo</small>
              </article>
              <article className="lab-stat">
                <span>Fuente única (single_source)</span>
                <strong>{result.data.reconciliation.singleSourceCount}</strong>
                <small>Confianza más baja: solo una fuente reportó el dato</small>
              </article>
              <article className="lab-stat">
                <span>Conflictos</span>
                <strong>{result.data.reconciliation.conflictCount}</strong>
                <small>Valores objetivos en desacuerdo, nunca promediados</small>
              </article>
              <article className="lab-stat">
                <span>Identidades sin resolver</span>
                <strong>{result.data.reconciliation.unresolvedCount}</strong>
                <small>Mejor sin vincular que vinculado incorrectamente</small>
              </article>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
