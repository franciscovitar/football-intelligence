import type { Metadata } from "next";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { formatDateTime } from "@/lib/player-display";
import { getDataMeshHealth } from "@/lib/queries/data-mesh";
import {
  getCoverageMatrix,
  summarizeCoverageStates,
  type CoverageState,
} from "@/lib/queries/coverage";

export const metadata: Metadata = { title: "Fuentes de datos" };

const SOURCE_TYPE_LABELS: Record<string, string> = {
  objective_structured: "Estructurada objetiva",
  objective_official: "Oficial objetiva",
  objective_web: "Web objetiva",
  qualitative_expert: "Cualitativa (experta)",
  qualitative_fan: "Cualitativa (hinchada)",
};

const COVERAGE_STATE_LABELS: Record<CoverageState, string> = {
  current_available: "ACTUAL",
  historical_only: "HISTÓRICO",
  previous_season: "TEMPORADA ANTERIOR",
  partial: "PARCIAL",
  token_required: "TOKEN",
  not_probed: "SIN PROBAR",
  missing: "FALTANTE",
  unsupported: "NO SOPORTADO",
};

// Static, documented facts about each source's cost, freshness role, known
// response/file limits, and provenance -- not derived from any live probe,
// so a source with zero coverage rows this run still discloses honestly
// what kind of source it is and what it structurally caps at.
interface ProviderInfo {
  cost: string;
  role: string;
  limits: string;
  provenance: string;
}

const PROVIDER_INFO: Record<string, ProviderInfo> = {
  thesportsdb: {
    cost: "Gratis (clave de prueba pública)",
    role: "Actual",
    limits: "lookupeventstats.php: máx. 5 filas · lookuplineup.php: máx. 5 jugadores por partido",
    provenance: "API JSON documentada (thesportsdb.com/documentation)",
  },
  openligadb: {
    cost: "Gratis, sin clave",
    role: "Actual",
    limits: "Sin límite documentado conocido",
    provenance: "API JSON pública (openligadb.de)",
  },
  "statsbomb-open": {
    cost: "Gratis (dataset abierto)",
    role: "Histórico/profundo — nunca satisface una necesidad actual",
    limits: "Subconjunto real de partidos publicados, no la temporada completa",
    provenance: "StatsBomb Open Data (github.com/statsbomb/open-data)",
  },
  "football-data-org": {
    cost: "Gratis con token opcional (tier Free)",
    role: "Actual",
    limits: "10 solicitudes/min · sin estadísticas de jugador en el tier Free",
    provenance: "API JSON documentada (api.football-data.org)",
  },
  "football-data-uk": {
    cost: "Gratis, sin clave",
    role: "Actual",
    limits: "Archivo CSV de resultados por temporada, sin datos de jugador",
    provenance: "Archivos CSV publicados, no scraping (football-data.co.uk)",
  },
  "api-football": {
    cost: "Pago (no usado por el Coverage Lab)",
    role: "—",
    limits: "—",
    provenance: "API JSON documentada (api-football.com)",
  },
};

export default async function SourcesPage() {
  await connection();
  const [result, coverageResult] = await Promise.all([getDataMeshHealth(), getCoverageMatrix()]);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">SOURCES / DATA COVERAGE</p>
          <h1>Fuentes y cobertura</h1>
          <p>
            Estado real de la malla multi-fuente (Block 13 PoC): qué fuentes están activas,
            qué observan, dónde coinciden y dónde entran en conflicto. Estos datos de
            reconciliación todavía NO alimentan las tablas canónicas de fútbol ni los scores V2.
            El estado de producto se mantiene separado del estado técnico de la malla.
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
                      <th>Costo</th>
                      <th>Rol</th>
                      <th>Límites conocidos</th>
                      <th>Procedencia</th>
                      <th>Tipo(s)</th>
                      <th>Observaciones</th>
                      <th>Última observación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.sources.map((source) => {
                      const info = PROVIDER_INFO[source.code];
                      return (
                        <tr key={source.code}>
                          <td>
                            {source.displayName} ({source.code})
                          </td>
                          <td>{source.isActive ? "Activa" : "Inactiva"}</td>
                          <td>{info?.cost ?? "—"}</td>
                          <td>{info?.role ?? "—"}</td>
                          <td>{info?.limits ?? "—"}</td>
                          <td>{info?.provenance ?? "—"}</td>
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
                      );
                    })}
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

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">COVERAGE LAB · V0</p>
                <h2>Cobertura por competición y fuente</h2>
              </div>
              <p>
                Una fuente histórica (StatsBomb Open Data) nunca satisface una necesidad de
                datos actuales, aunque soporte la métrica. Una fuente actual cuya sonda solo
                verificó la última temporada completa (no la vigente) se muestra como
                &ldquo;TEMPORADA ANTERIOR&rdquo;, nunca como &ldquo;ACTUAL&rdquo;. Sin token
                configurado, football-data.org se muestra como &ldquo;TOKEN&rdquo;, nunca como
                error.
              </p>
              <p>
                El catálogo objetivo conserva las nueve granularidades. El denominador se calcula
                desde las identidades únicas del catálogo por las 10 competiciones, sin un total
                hardcodeado. Un porcentaje menor refleja una vara estadística más completa.
              </p>
            </div>
            {coverageResult.status !== "ready" ? (
              <DataNotice title="Cobertura no disponible" message={coverageResult.message} />
            ) : coverageResult.data.cells.length === 0 ? (
              <p className="ranking-summary">
                Sin snapshot de cobertura todavía. Ejecutá el workflow manual Zero-Cost Coverage
                Lab (workflow_dispatch) para generarlo.
              </p>
            ) : (
              <>
                <p className="ranking-summary">
                  Última verificación:{" "}
                  {coverageResult.data.lastCheckedAt
                    ? formatDateTime(coverageResult.data.lastCheckedAt)
                    : "—"}
                </p>
                <div className="lab-card-grid">
                  <article className="lab-stat">
                    <span>Cobertura de producto · actual</span>
                    <strong>
                      {coverageResult.data.productCurrentCoverage.numerator}/
                      {coverageResult.data.productCurrentCoverage.denominator}
                    </strong>
                    <small>
                      Requisitos (competición × métrica) cubiertos por al menos una fuente actual,
                      sin importar cuántos proveedores existan
                    </small>
                  </article>
                  <article className="lab-stat">
                    <span>Cobertura de producto · temporada anterior</span>
                    <strong>
                      {coverageResult.data.productRecentSeasonCoverage.numerator}/
                      {coverageResult.data.productRecentSeasonCoverage.denominator}
                    </strong>
                    <small>
                      Una fuente actual verificó la última temporada completa, no la vigente —
                      evidencia real, pero nunca cuenta como cobertura actual
                    </small>
                  </article>
                  <article className="lab-stat">
                    <span>Cobertura de producto · histórica profunda</span>
                    <strong>
                      {coverageResult.data.productHistoricalCoverage.numerator}/
                      {coverageResult.data.productHistoricalCoverage.denominator}
                    </strong>
                    <small>Nunca satisfecha por una fuente actual, aunque soporte la métrica</small>
                  </article>
                  <article className="lab-stat">
                    <span>Filas de proveedor evaluadas (diagnóstico)</span>
                    <strong>{coverageResult.data.providerEntryCount}</strong>
                    <small>
                      Crece con el número de proveedores; no es el catálogo de métricas del
                      producto
                    </small>
                  </article>
                </div>
                <div className="lab-table-wrap">
                  <table className="lab-table">
                    <thead>
                      <tr>
                        <th>Competición</th>
                        {coverageResult.data.providers.map((provider) => (
                          <th key={provider.code}>
                            {provider.displayName}
                            <br />
                            <small>
                              {provider.freshnessRole === "current" ? "actual" : "histórico"}
                            </small>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {coverageResult.data.competitionCodes.map((competitionCode) => (
                        <tr key={competitionCode}>
                          <td>{competitionCode}</td>
                          {coverageResult.data.providers.map((provider) => {
                            const cell = coverageResult.data.cells.find(
                              (item) =>
                                item.competitionCode === competitionCode &&
                                item.providerCode === provider.code,
                            );
                            if (!cell) {
                              return (
                                <td key={provider.code}>
                                  <span className="dimension-chip">
                                    {COVERAGE_STATE_LABELS.not_probed}
                                  </span>
                                </td>
                              );
                            }
                            // Honest per-cell summary: every non-zero state,
                            // never a single majority-derived verdict -- a
                            // provider covering 2/48 metrics must never
                            // collapse to a single "NO SOPORTADO" badge.
                            const summaryText = summarizeCoverageStates(cell.stateCounts)
                              .map(({ state, count }) => `${count} ${COVERAGE_STATE_LABELS[state]}`)
                              .join(" · ");
                            return <td key={provider.code}>{summaryText}</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </>
      )}
    </main>
  );
}
