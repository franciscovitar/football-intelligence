import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import {
  formatConfidence,
  formatDateTime,
  formatScore,
  METRIC_LABELS,
  ROLE_LABELS,
  WINDOW_LABELS,
} from "@/lib/player-display";
import { getLabData } from "@/lib/queries/player-analytics";
import { getTeamLabData } from "@/lib/queries/team-analytics";
import { TEAM_WINDOW_LABELS } from "@/lib/team-display";

export const metadata: Metadata = {
  title: "Diagnostics Lab",
};

export default async function LabPage() {
  await connection();

  if (process.env.NODE_ENV === "production" && process.env.INTERNAL_LAB_ENABLED !== "true") {
    notFound();
  }

  const [result, teamResult] = await Promise.all([getLabData(), getTeamLabData()]);

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">INTERNAL DIAGNOSTICS</p>
          <h1>Lab</h1>
          <p>
            Estado del read model. No muestra credenciales ni detalles de infraestructura sensibles.
          </p>
        </div>
        <span className="internal-badge">internal</span>
      </section>

      {result.status !== "ready" ? (
        <DataNotice
          title={result.status === "unconfigured" ? "PostgreSQL no configurado" : "Diagnóstico no disponible"}
          message={result.message}
        />
      ) : result.data.activeContext === null ? (
        <DataNotice
          title="Sin snapshots"
          message="La conexión funciona, pero todavía no existen scores de Player Analytics."
        />
      ) : (
        <>
          <section className="context-strip">
            <div>
              <span>Scope activo</span>
              <strong>{result.data.activeContext.scopeKey}</strong>
            </div>
            <div>
              <span>Modelo</span>
              <strong>{result.data.activeContext.modelVersion}</strong>
            </div>
            <div>
              <span>Último cálculo</span>
              <strong>{formatDateTime(result.data.activeContext.calculatedAt)}</strong>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">SNAPSHOTS</p>
                <h2>Scopes disponibles</h2>
              </div>
            </div>
            <div className="lab-table-wrap">
              <table className="lab-table">
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Modelo</th>
                    <th>Jugadores</th>
                    <th>Score rows</th>
                    <th>Calculado</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.contexts.map((context) => (
                    <tr key={`${context.scopeKey}-${context.modelVersion}`}>
                      <td>{context.scopeKey}</td>
                      <td>{context.modelVersion}</td>
                      <td>{context.players}</td>
                      <td>{context.scoreRows}</td>
                      <td>{formatDateTime(context.calculatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">POPULATION</p>
                <h2>Muestras por rol y ventana</h2>
              </div>
            </div>
            <div className="lab-card-grid">
              {result.data.populations.map((population) => (
                <article className="lab-stat" key={`${population.window}-${population.role}`}>
                  <span>
                    {WINDOW_LABELS[population.window]} · {ROLE_LABELS[population.role]}
                  </span>
                  <strong>{population.players}</strong>
                  <small>
                    score medio {formatScore(population.averageScore)} · confianza{" "}
                    {formatConfidence(population.averageConfidence)}
                  </small>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">FEATURE COVERAGE</p>
                <h2>Métricas persistidas · season</h2>
              </div>
            </div>
            <div className="lab-table-wrap">
              <table className="lab-table">
                <thead>
                  <tr>
                    <th>Métrica</th>
                    <th>Jugadores</th>
                    <th>Feature rows</th>
                    <th>Muestra ref. media</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.metrics.map((metric) => (
                    <tr key={metric.metricName}>
                      <td>{METRIC_LABELS[metric.metricName] ?? metric.metricName}</td>
                      <td>{metric.players}</td>
                      <td>{metric.featureRows}</td>
                      <td>{Math.round(metric.averageReferenceSample)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {teamResult.status === "ready" && teamResult.data.contexts.length > 0 ? (
            <>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">TEAM SNAPSHOTS</p>
                    <h2>Scopes por competición</h2>
                  </div>
                </div>
                <div className="lab-table-wrap">
                  <table className="lab-table">
                    <thead><tr><th>Competición</th><th>Temporada</th><th>Equipos</th><th>Scores</th><th>Elo rows</th></tr></thead>
                    <tbody>
                      {teamResult.data.contexts.map((context) => (
                        <tr key={`${context.scopeKey}-${context.modelVersion}`}>
                          <td>{context.competitionCode}</td><td>{context.seasonLabel}</td>
                          <td>{context.teams}</td><td>{context.scoreRows}</td><td>{context.eloRows}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="panel">
                <div className="section-heading"><div><p className="eyebrow">TEAM POPULATION</p><h2>Cobertura por ventana</h2></div></div>
                <div className="lab-card-grid">
                  {teamResult.data.populations.map((population) => (
                    <article className="lab-stat" key={`${population.scopeKey}-${population.window}`}>
                      <span>{population.competitionCode} · {population.seasonLabel} · {TEAM_WINDOW_LABELS[population.window]}</span>
                      <strong>{population.teams}</strong>
                      <small>score medio {formatScore(population.averageScore)} · confianza {formatConfidence(population.averageConfidence)}</small>
                    </article>
                  ))}
                </div>
              </section>
            </>
          ) : null}
        </>
      )}
    </main>
  );
}
