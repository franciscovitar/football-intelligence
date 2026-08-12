import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

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

  const [result, metaResult] = await Promise.all([
    getPlayerDetail(playerId),
    getPlayerMeta(playerId),
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
  const seasonScore = scores.find((score) => score.window === "season") ?? scores[0];
  const primaryWindow: AnalyticsWindow = scores.some((score) => score.window === "last_5")
    ? "last_5"
    : "season";
  const primaryFeatures = featuresForWindow(features, primaryWindow);
  const strengths = primaryFeatures.slice(0, 4);
  const watchItems = [...primaryFeatures].sort((a, b) => a.percentile - b.percentile).slice(0, 4);

  return (
    <main className="page-shell">
      <div className="back-row">
        <Link href="/rankings">← Volver a rankings</Link>
      </div>

      <section className="player-hero">
        <div>
          <p className="eyebrow">{ROLE_LABELS_SINGULAR[seasonScore.role]}</p>
          <h1>{player.playerName}</h1>
          <div className="player-facts">
            {player.latestTeam ? <span>Último equipo registrado · {player.latestTeam}</span> : null}
            {player.nationalityCode ? <span>Nacionalidad · {player.nationalityCode}</span> : null}
            {player.dateOfBirth ? <span>Nacimiento · {player.dateOfBirth}</span> : null}
          </div>
          <p className="player-context">
            {context.scopeKey} · {context.modelVersion} · {formatDateTime(context.calculatedAt)}
          </p>
        </div>

        <div className="player-score-hero">
          <span>Performance</span>
          <strong>{formatScore(seasonScore.overallScore)}</strong>
          <small>Confianza {formatConfidence(seasonScore.confidence)}</small>
          <div className="confidence-track wide" aria-hidden="true">
            <span style={{ width: `${Math.round(seasonScore.confidence * 100)}%` }} />
          </div>
        </div>
      </section>

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
                <strong>{formatScore(score.overallScore)}</strong>
                <small>
                  {score.appearances} PJ · {score.minutes} min · conf.{" "}
                  {formatConfidence(score.confidence)}
                </small>
              </article>
            );
          })}
        </div>
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

      <section className="player-analysis-grid">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SKILL PROFILE</p>
              <h2>Dimensiones</h2>
            </div>
            <p>Percentiles agregados del rol.</p>
          </div>
          <div className="dimension-list">
            {Object.entries(seasonScore.dimensionScores)
              .sort((a, b) => b[1] - a[1])
              .map(([dimension, value]) => (
                <div className="dimension-row" key={dimension}>
                  <div>
                    <span>{DIMENSION_LABELS[dimension] ?? dimension}</span>
                    <strong>{formatScore(value)}</strong>
                  </div>
                  <div className="percentile-track" aria-hidden="true">
                    <span style={{ width: `${Math.round(value)}%` }} />
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
    </main>
  );
}
