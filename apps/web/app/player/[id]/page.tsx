import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { DiagnosticFindingCard } from "@/features/diagnostics/finding-card";
import { PerceptionEvidenceCard } from "@/features/perception/evidence-card";
import { DataNotice } from "@/features/players/data-notice";
import { formatSigned, SURPRISE_LABELS, TREND_LABELS, WATCHLIST_LABELS } from "@/lib/meta-display";
import {
  DIMENSION_LABELS,
  formatConfidence,
  formatDateTime,
  formatPer90,
  formatScore,
  METRIC_LABELS,
  ROLE_LABELS_SINGULAR,
  WINDOW_LABELS,
} from "@/lib/player-display";
import { getPlayerMeta } from "@/lib/queries/meta-analytics";
import { getEntityDiagnostics, type DiagnosticFinding } from "@/lib/queries/diagnostics";
import { getPlayerPerceptionEvidence } from "@/lib/queries/perception";
import { getPlayerRating } from "@/lib/queries/rating-intelligence";
import { RATING_SIGNAL_LABELS } from "@/lib/rating-display";
import { getPlayerSeasonStats } from "@/lib/queries/season-stats";
import {
  formatSeasonStat,
  SEASON_STAT_LABELS,
  SEASON_STAT_ORDER,
} from "@/lib/season-stats-display";
import {
  getPlayerDetail,
  type AnalyticsWindow,
  type PlayerFeature,
} from "@/lib/queries/player-analytics";

export const metadata: Metadata = {
  title: "Detalle de jugador",
};

const WINDOW_ORDER: AnalyticsWindow[] = ["season", "last_10", "last_5", "last_3"];

function validId(raw: string): number | null {
  if (!/^[1-9]\d*$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function featuresForWindow(features: PlayerFeature[], window: AnalyticsWindow): PlayerFeature[] {
  return features
    .filter((feature) => feature.window === window)
    .sort((a, b) => b.percentile - a.percentile);
}

function findByCode(findings: DiagnosticFinding[], code: string): DiagnosticFinding | undefined {
  return findings.find((finding) => finding.diagnosticCode === code);
}

function metricNumber(finding: DiagnosticFinding, key: string): number | null {
  const value = finding.supportingMetrics[key];
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await connection();
  const { id } = await params;
  const playerId = validId(id);

  if (playerId === null) {
    notFound();
  }

  const [result, metaResult, perceptionResult, ratingResult, diagnosticsResult, seasonStatsResult] =
    await Promise.all([
      getPlayerDetail(playerId),
      getPlayerMeta(playerId),
      getPlayerPerceptionEvidence(playerId),
      getPlayerRating(playerId),
      getEntityDiagnostics("player", playerId),
      getPlayerSeasonStats(playerId),
    ]);

  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <div className="back-row">
          <Link href="/rankings">← Volver a rankings</Link>
        </div>
        <DataNotice
          title={result.status === "unconfigured" ? "Base de datos pendiente" : "No pudimos cargar el jugador"}
          message={result.message}
        />
      </main>
    );
  }

  if (!result.data) {
    notFound();
  }

  const { player, scores, features, context } = result.data;
  const hasScoreEvidence = scores.length > 0;
  const hasReadyScore = scores.some(
    (score) => score.evidenceState === "ready" && score.overallScore !== null,
  );
  const seasonScore = scores.find((score) => score.window === "season") ?? scores[0];
  const primaryWindow: AnalyticsWindow = scores.some((score) => score.window === "last_5")
    ? "last_5"
    : "season";
  const primaryFeatures = featuresForWindow(features, primaryWindow);
  const strengths = primaryFeatures.slice(0, 4);
  const watchItems = [...primaryFeatures].sort((a, b) => a.percentile - b.percentile).slice(0, 4);

  const diagnostics = diagnosticsResult.status === "ready" ? diagnosticsResult.data : [];
  const finishingFinding =
    findByCode(diagnostics, "finishing_underperformance") ??
    findByCode(diagnostics, "finishing_overperformance");
  const seasonStats = seasonStatsResult.status === "ready" ? seasonStatsResult.data : null;

  return (
    <main className="page-shell">
      <div className="back-row">
        <Link href="/rankings">← Volver a rankings</Link>
      </div>

      <section className="player-hero">
        <div>
          <p className="eyebrow">
            {hasScoreEvidence ? ROLE_LABELS_SINGULAR[seasonScore.role] : "JUGADOR"}
          </p>
          <h1>{player.playerName}</h1>
          <div className="player-facts">
            {player.latestTeam ? <span>Último equipo registrado · {player.latestTeam}</span> : null}
            {player.nationalityCode ? <span>Nacionalidad · {player.nationalityCode}</span> : null}
            {player.dateOfBirth ? <span>Nacimiento · {player.dateOfBirth}</span> : null}
          </div>
          {hasScoreEvidence ? (
            <p className="player-context">
              {context.scopeKey} · {context.modelVersion} · {formatDateTime(context.calculatedAt)}
            </p>
          ) : (
            <p className="player-context">
              Score real insuficiente: la evidencia disponible no alcanza el perfil mínimo. Los
              datos smoke/test no se muestran como producto.
            </p>
          )}
        </div>

        {hasReadyScore ? (
          <div className="player-score-hero">
            <span>Performance</span>
            <strong>{formatScore(seasonScore.overallScore ?? 0)}</strong>
            <small>Confianza {formatConfidence(seasonScore.confidence)}</small>
            <small>Evidencia disponible {Math.round(seasonScore.evidenceCoveragePct)}%</small>
            <div className="confidence-track wide" aria-hidden="true">
              <span style={{ width: `${Math.round(seasonScore.confidence * 100)}%` }} />
            </div>
          </div>
        ) : null}
      </section>

      {hasReadyScore ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">TREND</p>
              <h2>Performance vs Forma</h2>
            </div>
            <p>Las ventanas recientes pesan más los partidos más cercanos.</p>
          </div>
          <div className="window-grid">
            {WINDOW_ORDER.map((window) => {
              const score = scores.find((candidate) => candidate.window === window);
              if (!score) {
                return null;
              }
              return (
                <article className="window-card" key={window}>
                  <span>{WINDOW_LABELS[window]}</span>
                  <strong>
                    {score.overallScore === null
                      ? score.evidenceState
                      : formatScore(score.overallScore)}
                  </strong>
                  <small>
                    {score.appearances} PJ · {score.minutes} min · conf.{" "}
                    {formatConfidence(score.confidence)}
                  </small>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DIAGNOSTIC RULES</p>
            <h2>Resultados vs. rendimiento subyacente</h2>
          </div>
          <p>Goles reales contra xG. No implica suerte, mérito ni una predicción futura.</p>
        </div>
        {finishingFinding ? (
          <div className="window-grid">
            <article className="window-card">
              <span>Goles</span>
              <strong>{formatScore(metricNumber(finishingFinding, "goals") ?? 0)}</strong>
              <small>P{Math.round(metricNumber(finishingFinding, "goals_percentile") ?? 0)}</small>
            </article>
            <article className="window-card">
              <span>xG</span>
              <strong>{formatScore(metricNumber(finishingFinding, "xg") ?? 0)}</strong>
              <small>P{Math.round(metricNumber(finishingFinding, "xg_percentile") ?? 0)}</small>
            </article>
            <article className="window-card">
              <span>Lectura</span>
              <strong>
                {finishingFinding.diagnosticCode === "finishing_underperformance"
                  ? "Por debajo del proceso"
                  : "Por encima del proceso"}
              </strong>
              <small>Confianza {formatConfidence(finishingFinding.confidence)}</small>
            </article>
          </div>
        ) : (
          <p className="ranking-summary">Sin datos suficientes de xG para esta comparación.</p>
        )}
      </section>

      {metaResult.status === "ready" && metaResult.data ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">EXPECTATION & META</p>
              <h2>Expectativa histórica y nivel estable</h2>
            </div>
            <p>El baseline histórico no es una predicción ni una valoración de mercado.</p>
          </div>
          <div className="window-grid">
            <article className="window-card">
              <span>Nivel estable</span>
              <strong>{formatScore(metaResult.data.stableScore)}</strong>
              <small>conf. {formatConfidence(metaResult.data.stableConfidence)}</small>
            </article>
            <article className="window-card">
              <span>Expectativa histórica</span>
              <strong>{metaResult.data.expectationScore === null ? "—" : formatScore(metaResult.data.expectationScore)}</strong>
              <small>{SURPRISE_LABELS[metaResult.data.surpriseSignal] ?? metaResult.data.surpriseSignal} · {formatSigned(metaResult.data.surpriseDelta)}</small>
            </article>
            <article className="window-card">
              <span>Tendencia</span>
              <strong>{formatSigned(metaResult.data.trendDelta)}</strong>
              <small>{TREND_LABELS[metaResult.data.trendSignal] ?? metaResult.data.trendSignal}</small>
            </article>
            <article className="window-card">
              <span>Watchlist</span>
              <strong>{formatScore(metaResult.data.watchlistScore)}</strong>
              <small>{WATCHLIST_LABELS[metaResult.data.watchlistSignal] ?? metaResult.data.watchlistSignal}</small>
            </article>
          </div>
        </section>
      ) : null}

      {perceptionResult.status === "ready" ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">PERCEPTION INTELLIGENCE</p>
              <h2>Percepción externa</h2>
            </div>
            <p>Evidencia externa con provenance. No es un score ni implica consenso.</p>
          </div>
          {perceptionResult.data.length === 0 ? (
            <p className="ranking-summary">
              Todavía no hay evidencia externa vinculada de forma inequívoca.
            </p>
          ) : (
            <div className="ranking-list">
              {perceptionResult.data.map((item) => (
                <PerceptionEvidenceCard evidence={item} key={item.evidenceId} />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {ratingResult.status === "ready" && ratingResult.data ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">RATING INTELLIGENCE</p>
              <h2>Rendimiento vs percepción</h2>
            </div>
            <p>
              {RATING_SIGNAL_LABELS[ratingResult.data.ratingSignal] ??
                ratingResult.data.ratingSignal}. No es valor de mercado.
            </p>
          </div>
          <div className="window-grid">
            <article className="window-card">
              <span>Nivel estable</span>
              <strong>{formatScore(ratingResult.data.performanceScore)}</strong>
              <small>conf. {formatConfidence(ratingResult.data.performanceConfidence)}</small>
            </article>
            <article className="window-card">
              <span>Percepción</span>
              <strong>
                {ratingResult.data.perceptionScore === null
                  ? "—"
                  : formatScore(ratingResult.data.perceptionScore)}
              </strong>
              <small>conf. {formatConfidence(ratingResult.data.perceptionConfidence)}</small>
            </article>
            <article className="window-card">
              <span>Gap</span>
              <strong>{formatSigned(ratingResult.data.ratingGap)}</strong>
              <small>conf. {formatConfidence(ratingResult.data.ratingConfidence)}</small>
            </article>
            <article className="window-card">
              <span>Consenso / polarización</span>
              <strong>
                {ratingResult.data.consensusScore === null
                  ? "—"
                  : formatScore(ratingResult.data.consensusScore)}
              </strong>
              <small>
                pol. {ratingResult.data.polarizationScore === null
                  ? "—"
                  : formatScore(ratingResult.data.polarizationScore)}
              </small>
            </article>
          </div>
        </section>
      ) : null}
      {hasScoreEvidence ? (
        <section className="player-analysis-grid">
          <div className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">SKILL PROFILE V2</p>
                <h2>Dimensiones</h2>
              </div>
              <p>La evidencia faltante se muestra como estado, nunca como cero.</p>
            </div>
            <div className="dimension-list">
              {Object.entries(seasonScore.dimensionEvidence).map(([dimension, evidence]) => (
                  <div className="dimension-row" key={dimension}>
                    <div>
                      <span>{DIMENSION_LABELS[dimension] ?? dimension}</span>
                      <strong>
                        {evidence.score === null
                          ? evidence.evidenceState
                          : formatScore(evidence.score)}
                      </strong>
                      <small>Evidencia {Math.round(evidence.evidenceCoveragePct)}%</small>
                    </div>
                    <div className="percentile-track" aria-hidden="true">
                      <span style={{ width: `${Math.round(evidence.score ?? 0)}%` }} />
                    </div>
                  </div>
                ))}
            </div>
          </div>

          <div className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">EVIDENCIA</p>
                <h2>Fortalezas · {WINDOW_LABELS[primaryWindow]}</h2>
              </div>
            </div>
            <div className="metric-list">
              {strengths.map((feature) => (
                <div className="metric-row" key={`${feature.window}-${feature.metricName}`}>
                  <div>
                    <strong>{METRIC_LABELS[feature.metricName] ?? feature.metricName}</strong>
                    <span>
                      {formatPer90(feature.adjustedPer90)} /90 · muestra {feature.referenceSampleSize}
                    </span>
                  </div>
                  <span className="metric-percentile">P{Math.round(feature.percentile)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {seasonStats ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">REAL SEASON DATA</p>
              <h2>Datos reales de temporada · {seasonStats.seasonLabel}</h2>
            </div>
            <p>Observación directa de la fuente, no una estimación del modelo.</p>
          </div>
          <div className="metric-grid">
            {SEASON_STAT_ORDER.map((key) => (
              <article className="metric-tile" key={key}>
                <span>{SEASON_STAT_LABELS[key]}</span>
                <strong>{formatSeasonStat(seasonStats[key])}</strong>
              </article>
            ))}
          </div>
          <p className="ranking-summary">
            Fuente: {seasonStats.source} · actualizado {formatDateTime(seasonStats.retrievedAt)}
          </p>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DIAGNOSTIC RULES</p>
            <h2>Diagnósticos</h2>
          </div>
          <p>Reglas deterministas sobre evidencia ya calculada. No son una predicción.</p>
        </div>
        {diagnostics.length === 0 ? (
          <p className="ranking-summary">Sin hallazgos relevantes en esta ventana.</p>
        ) : (
          <div className="ranking-list">
            {diagnostics.map((finding) => (
              <DiagnosticFindingCard
                finding={finding}
                key={`${finding.diagnosticCode}-${finding.comparisonGroup}-${finding.windowKey}`}
              />
            ))}
          </div>
        )}
      </section>

      {hasReadyScore ? (
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CONTEXT</p>
            <h2>Qué explica y qué no explica el score</h2>
          </div>
        </div>
        <div className="explanation-grid">
          <article>
            <h3>Comparación justa</h3>
            <p>
              Los percentiles se calculan contra futbolistas del mismo rol. Los eventos defensivos
              ajustan oportunidades según posesión y las muestras chicas se estabilizan con shrinkage.
            </p>
          </article>
          <article>
            <h3>Confianza separada</h3>
            <p>
              El score mide rendimiento; la confianza mide cuánto deberíamos creerle. Minutos, rol,
              población comparable y cobertura de métricas afectan esa confianza.
            </p>
          </article>
          <article>
            <h3>Límites V1</h3>
            <p>
              No hay xG/xA, tracking ni ajuste por fuerza de rival todavía. El modelo de arqueros es
              provisional y el ajuste de rivales llega en bloques posteriores.
            </p>
          </article>
        </div>
      </section>
      ) : null}

      {hasReadyScore ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">WATCH</p>
              <h2>Métricas para mirar</h2>
            </div>
            <p>No son “debilidades” automáticas: también pueden reflejar rol o estilo.</p>
          </div>
          <div className="metric-grid">
            {watchItems.map((feature) => (
              <article className="metric-tile" key={`${feature.window}-${feature.metricName}`}>
                <span>{METRIC_LABELS[feature.metricName] ?? feature.metricName}</span>
                <strong>P{Math.round(feature.percentile)}</strong>
                <small>
                  raw {formatPer90(feature.rawPer90)} /90 · adj.{" "}
                  {formatPer90(feature.adjustedPer90)} /90
                </small>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
