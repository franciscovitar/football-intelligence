import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { DataNotice } from "@/features/players/data-notice";
import { formatConfidence, formatDateTime, formatScore } from "@/lib/player-display";
import {
  getTeamDetail,
  type TeamFeature,
  type TeamWindow,
} from "@/lib/queries/team-analytics";
import {
  DIAGNOSTIC_LABELS,
  diagnosticSignals,
  formatTeamMetric,
  RESULTS_PROCESS_LABELS,
  TEAM_DIMENSION_LABELS,
  TEAM_METRIC_LABELS,
  TEAM_WINDOW_LABELS,
} from "@/lib/team-display";

export const metadata: Metadata = { title: "Detalle de equipo" };
const WINDOW_ORDER: TeamWindow[] = ["season", "last_10", "last_5", "last_3"];

function validId(raw: string): number | null {
  if (!/^[1-9]\d*$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function featuresForWindow(features: TeamFeature[], window: TeamWindow): TeamFeature[] {
  return features.filter((item) => item.window === window);
}

function resultLabel(value: number): string {
  if (value === 1) return "G";
  if (value === 0.5) return "E";
  return "P";
}

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const teamId = validId(id);
  if (teamId === null) notFound();
  const competitionCode = firstValue(query.competition).trim().slice(0, 32);
  const result = await getTeamDetail(teamId, competitionCode);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <div className="back-row"><Link href="/teams">← Volver a equipos</Link></div>
        <DataNotice title={result.status === "unconfigured" ? "Base de datos pendiente" : "No pudimos cargar el equipo"} message={result.message} />
      </main>
    );
  }
  if (!result.data) notFound();

  const { team, context, scores, features, eloHistory } = result.data;
  const seasonScore = scores.find((item) => item.window === "season") ?? scores[0];
  const primaryWindow: TeamWindow = scores.some((item) => item.window === "last_5") ? "last_5" : "season";
  const primaryFeatures = featuresForWindow(features, primaryWindow);
  const signals = diagnosticSignals(seasonScore.diagnostics);
  const evidence = [...primaryFeatures].sort((a, b) => b.percentile - a.percentile);

  return (
    <main className="page-shell">
      <div className="back-row">
        <Link href={`/teams?competition=${encodeURIComponent(context.competitionCode)}`}>← Volver a equipos</Link>
      </div>
      <section className="player-hero">
        <div>
          <p className="eyebrow">{context.competitionName} · {context.seasonLabel}</p>
          <h1>{team.teamName}</h1>
          <div className="player-facts">
            <span>Elo {Math.round(seasonScore.currentElo)}</span>
            <span>Trend últimos 5 {seasonScore.eloChangeLast5 >= 0 ? "+" : ""}{seasonScore.eloChangeLast5.toFixed(1)}</span>
            <span>{seasonScore.matches} partidos</span>
          </div>
          <p className="player-context">{context.scopeKey} · {context.modelVersion} · {formatDateTime(context.calculatedAt)}</p>
        </div>
        <div className="player-score-hero">
          <span>Performance</span>
          <strong>{formatScore(seasonScore.overallScore)}</strong>
          <small>Confianza {formatConfidence(seasonScore.confidence)}</small>
          <div className="confidence-track wide" aria-hidden="true"><span style={{ width: `${Math.round(seasonScore.confidence * 100)}%` }} /></div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">TREND</p><h2>Performance, Forma y Elo</h2></div><p>Las ventanas recientes tienen half-life de 3 partidos.</p></div>
        <div className="window-grid">
          {WINDOW_ORDER.map((window) => {
            const score = scores.find((item) => item.window === window);
            return score ? (
              <article className="window-card" key={window}>
                <span>{TEAM_WINDOW_LABELS[window]}</span><strong>{formatScore(score.overallScore)}</strong>
                <small>{score.matches} PJ · conf. {formatConfidence(score.confidence)} · Elo {Math.round(score.currentElo)}</small>
              </article>
            ) : null;
          })}
        </div>
      </section>

      <section className="player-analysis-grid">
        <div className="panel">
          <div className="section-heading"><div><p className="eyebrow">TEAM PROFILE</p><h2>Dimensiones</h2></div><p>Percentiles dentro de la competición.</p></div>
          <div className="dimension-list">
            {Object.entries(seasonScore.dimensionScores).sort((a, b) => b[1] - a[1]).map(([name, value]) => (
              <div className="dimension-row" key={name}>
                <div><span>{TEAM_DIMENSION_LABELS[name] ?? name}</span><strong>{formatScore(value)}</strong></div>
                <div className="percentile-track" aria-hidden="true"><span style={{ width: `${Math.round(value)}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="section-heading"><div><p className="eyebrow">RESULTS VS PROCESS</p><h2>{RESULTS_PROCESS_LABELS[seasonScore.resultsProcessSignal]}</h2></div></div>
          <p className="hero-copy team-copy">Delta {seasonScore.resultsProcessDelta >= 0 ? "+" : ""}{seasonScore.resultsProcessDelta.toFixed(1)}. No equivale automáticamente a suerte, mérito o merecimiento.</p>
          <div className="metric-list">
            {signals.length === 0 ? <p className="ranking-meta">No hay una señal fuerte adicional en esta ventana.</p> : signals.map((signal) => (
              <div className="metric-row" key={signal}><strong>{DIAGNOSTIC_LABELS[signal] ?? signal}</strong></div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">EVIDENCIA · {TEAM_WINDOW_LABELS[primaryWindow]}</p><h2>Qué está produciendo</h2></div><p>Missing permanece missing; cobertura visible por métrica.</p></div>
        <div className="metric-grid">
          {evidence.map((feature) => (
            <article className="metric-tile" key={`${feature.window}-${feature.metricName}`}>
              <span>{TEAM_METRIC_LABELS[feature.metricName] ?? feature.metricName}</span>
              <strong>{formatTeamMetric(feature.metricName, feature.adjustedValue)}</strong>
              <small>P{Math.round(feature.percentile)} · cobertura {feature.observedMatches}/{feature.matches}{feature.rawValue !== feature.adjustedValue ? ` · raw ${formatTeamMetric(feature.metricName, feature.rawValue)}` : ""}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">ELO</p><h2>Evolución partido a partido</h2></div><p>1500 inicial · K 20 · localía +60 · sin margen de victoria.</p></div>
        <div className="lab-table-wrap"><table className="lab-table"><thead><tr><th>Fecha</th><th>Rival</th><th>Resultado</th><th>Esperado</th><th>Pre</th><th>Post</th></tr></thead><tbody>
          {eloHistory.map((point) => <tr key={point.matchId}><td>{formatDateTime(point.kickoffAt)}</td><td>{point.opponentName}</td><td>{resultLabel(point.actualResult)}</td><td>{Math.round(point.expectedResult * 100)}%</td><td>{point.preMatchRating.toFixed(1)}</td><td>{point.postMatchRating.toFixed(1)}</td></tr>)}
        </tbody></table></div>
      </section>

      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">LIMITACIONES</p><h2>Cómo leer Team V1</h2></div></div>
        <div className="explanation-grid">
          <article><h3>Generación, no xG</h3><p>Tiros, tiros al arco, tiros en el área y corners miden volumen de ataque; no calidad esperada de ocasión.</p></article>
          <article><h3>Control proxy</h3><p>Posesión y pase describen control del balón, no superioridad táctica ni una forma universal de jugar bien.</p></article>
          <article><h3>Comparación local</h3><p>Scores y Elo se interpretan dentro de esta competición y temporada. No están calibrados entre ligas desconectadas.</p></article>
        </div>
      </section>
    </main>
  );
}
