import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { PerceptionEvidenceCard } from "@/features/perception/evidence-card";
import {
  Confidence,
  DimensionCard,
  EmptyState,
  EvidenceBadge,
  MetricRow,
  ScoreBadge,
  Section,
} from "@/features/product/product-ui";
import { selectPlayerContext } from "@/lib/player-context";
import {
  metricCategory,
  PLAYER_DIMENSION_LABELS,
  WINDOW_LABELS,
  formatNumber,
  humanMetric,
} from "@/lib/product-display";
import { getEntityDiagnostics } from "@/lib/queries/diagnostics";
import { getPlayerPerceptionEvidence } from "@/lib/queries/perception";
import { PLAYER_RANKING_DIMENSIONS } from "@/lib/queries/product-intelligence";
import {
  getScopedPlayerContexts,
  getScopedPlayerDetail,
} from "@/lib/queries/scoped-player-intelligence";

export const metadata: Metadata = { title: "Jugador V2" };
const value = (input: string | string[] | undefined) =>
  Array.isArray(input) ? (input[0] ?? "") : (input ?? "");

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const playerId = Number(id);
  if (!Number.isInteger(playerId) || playerId < 1) notFound();

  const contextsResult = await getScopedPlayerContexts();
  const contexts = contextsResult.status === "ready" ? contextsResult.data : [];
  const selectedContext = selectPlayerContext(contexts, value(query.context));
  if (!selectedContext) notFound();

  const [result, perceptionResult, diagnosticsResult] = await Promise.all([
    getScopedPlayerDetail(playerId, selectedContext.scopeKey),
    getPlayerPerceptionEvidence(playerId),
    getEntityDiagnostics("player", playerId),
  ]);
  if (result.status === "ready" && result.data === null) notFound();
  if (result.status !== "ready") {
    return (
      <main className="page-shell">
        <EmptyState
          title="Jugador V2 no disponible"
          missing={result.message}
          unlock="Este perfil solo se habilita con una observación real V2 dentro del contexto solicitado; no recurre a V1 ni a datos de prueba."
        />
      </main>
    );
  }
  const data = result.data;
  if (data === null) notFound();
  const season = data.windows.find((item) => item.window === "season") ?? data.windows[0];
  if (!season) notFound();

  const metrics = data.metrics[season.window];
  const grouped = Map.groupBy(metrics, metricCategory);
  const goals = metrics.find((item) => item.metricName === "goals");
  const xg = metrics.find((item) => ["xg", "expected_goals"].includes(item.metricName));
  const perception = perceptionResult.status === "ready" ? perceptionResult.data : [];
  const diagnostics = diagnosticsResult.status === "ready" ? diagnosticsResult.data : [];
  const contextQuery = encodeURIComponent(selectedContext.scopeKey);
  const dimensionEntries = PLAYER_RANKING_DIMENSIONS.filter(
    (dimension) => dimension !== "overall",
  ).map((dimension) => ({
    dimension,
    evidence: season.dimensions[dimension],
  }));
  const supportedDimensions = dimensionEntries.filter(
    ({ evidence }) =>
      evidence?.evidenceState === "ready" || evidence?.evidenceState === "partial",
  );
  const pendingDimensions = dimensionEntries.filter(
    ({ evidence }) =>
      evidence?.evidenceState !== "ready" && evidence?.evidenceState !== "partial",
  );

  return (
    <main className="page-shell">
      <section className="player-hero product-detail-hero">
        <div>
          <p className="eyebrow">
            PLAYER INTELLIGENCE · V2 REAL {selectedContext.isHistorical ? "· HISTÓRICO" : ""}
          </p>
          <h1>{data.player.playerName}</h1>
          <p>
            {data.player.teamName ?? "Equipo no disponible"} ·{" "}
            {data.player.competitionName ?? "Competición no disponible"} ·{" "}
            {data.player.seasonLabel ?? "Temporada no disponible"}
          </p>
          <div className="evidence-chips">
            <span>{season.positionFamily ?? season.role}</span>
            <span>{season.minutes} min</span>
            <span>{season.appearances} PJ</span>
            <span>{metrics.length} métricas reales</span>
            <span>{data.context.scopeKey}</span>
          </div>
        </div>
        <div>
          <ScoreBadge score={season.overallScore} state={season.evidenceState} />
          <Confidence value={season.confidence} coverage={season.evidenceCoveragePct} />
        </div>
      </section>

      <Section eyebrow="PRIMARY VERDICT" title="Qué podemos afirmar">
        <div className="verdict-copy">
          <EvidenceBadge state={season.evidenceState} />
          <p>
            {season.evidenceState === "ready"
              ? "El score superó los controles de muestra, cobertura y confianza para esta ventana."
              : season.evidenceState === "partial"
                ? "Hay dimensiones y métricas reales publicables, pero la cobertura todavía no alcanza para un Overall ni un ranking consolidado."
                : "Hay métricas directas reales para este jugador, pero todavía faltan dimensiones núcleo para publicar un Overall."}
          </p>
          <small>
            Modelo {data.context.modelVersion} · calculado{" "}
            {new Date(season.calculatedAt).toLocaleDateString("es-AR")} · contexto{" "}
            {selectedContext.competitionName} {selectedContext.seasonLabel}
          </small>
        </div>
      </Section>

      <Section eyebrow="DIMENSIONS" title="Dimensiones con evidencia publicable">
        {supportedDimensions.length ? (
          <div className="dimension-card-grid">
            {supportedDimensions.map(({ dimension, evidence }) => (
              <DimensionCard
                key={dimension}
                label={PLAYER_DIMENSION_LABELS[dimension]}
                evidence={evidence}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Todavía no hay una dimensión publicable"
            missing="El perfil sí contiene métricas directas, pero ninguna dimensión supera todavía sus requisitos de evidencia."
            unlock="Las métricas observadas se mantienen disponibles abajo; no se imputan scores para completar huecos."
            compact
          />
        )}
        {pendingDimensions.length ? (
          <div className="comparison-caveat">
            <strong>Dimensiones aún no evaluables</strong>
            <p>
              Estas dimensiones no reciben score porque faltan métricas núcleo o cobertura suficiente.
              Se mantienen separadas de la evidencia disponible en lugar de mostrarlas como valores cero.
            </p>
            <div className="evidence-chips">
              {pendingDimensions.map(({ dimension }) => (
                <span key={dimension}>{PLAYER_DIMENSION_LABELS[dimension]}</span>
              ))}
            </div>
          </div>
        ) : null}
      </Section>

      <Section eyebrow="STATISTICS" title="Métricas que sostienen la lectura">
        {metrics.length ? (
          <div className="metric-category-grid">
            {Array.from(grouped.entries()).map(([category, items]) => (
              <div className="metric-category" key={category}>
                <h3>{category}</h3>
                {items.map((metric) => (
                  <MetricRow
                    key={`${metric.metricGranularity}-${metric.metricName}`}
                    metric={metric}
                  />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Métricas fuente no disponibles"
            missing="El perfil existe, pero no hay features reales vinculadas a esta ventana."
            unlock="La fuente debe aportar valores observados; un campo ausente nunca se muestra como 0."
            compact
          />
        )}
      </Section>

      {goals && xg && goals.rawValue !== null && xg.rawValue !== null ? (
        <Section eyebrow="RESULTS VS PERFORMANCE" title="Output real y proceso subyacente">
          <div className="window-grid">
            <article className="window-card">
              <span>Goles</span>
              <strong>{formatNumber(goals.rawValue)}</strong>
              <small>Output observado</small>
            </article>
            <article className="window-card">
              <span>xG</span>
              <strong>{formatNumber(xg.rawValue)}</strong>
              <small>Output esperado</small>
            </article>
            <article className="window-card">
              <span>Diferencia</span>
              <strong>{formatNumber(goals.rawValue - xg.rawValue)}</strong>
              <small>
                {goals.rawValue >= xg.rawValue
                  ? "Conversión por encima del output esperado"
                  : "Resultados por debajo del proceso subyacente"}
              </small>
            </article>
          </div>
        </Section>
      ) : null}

      <Section eyebrow="FORM / WINDOWS" title="Cómo cambia la evidencia">
        {data.windows.length > 1 ? (
          <div className="window-grid">
            {data.windows.map((item) => (
              <article className="window-card" key={item.window}>
                <span>{WINDOW_LABELS[item.window]}</span>
                <strong>
                  {item.overallScore === null
                    ? `${Math.round(item.evidenceCoveragePct)}% evidencia`
                    : Math.round(item.overallScore)}
                </strong>
                <EvidenceBadge state={item.evidenceState} />
                <small>
                  {item.minutes} min · conf. {Math.round(item.confidence * 100)}%
                </small>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Sin tendencia publicable"
            missing="Solo existe una ventana de evidencia; no hay dos períodos comparables."
            unlock="Las ventanas last 3/5/10 se mostrarán cuando tengan muestra real suficiente."
            compact
          />
        )}
      </Section>

      <Section eyebrow="DIAGNOSTICS" title="Hallazgos deterministas">
        {diagnostics.length ? (
          <div className="signal-list">
            {diagnostics.map((item) => (
              <article key={`${item.diagnosticCode}-${item.windowKey}`}>
                <strong>{humanMetric(item.diagnosticCode)}</strong>
                <span>
                  {item.windowKey} · conf. {Math.round(item.confidence * 100)}%
                </span>
                <small>
                  {Object.entries(item.supportingMetrics)
                    .slice(0, 4)
                    .map(([key, metricValue]) => `${humanMetric(key)}: ${String(metricValue)}`)
                    .join(" · ")}
                </small>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Sin diagnóstico publicable"
            missing="Ninguna regla determinista produjo un hallazgo con evidencia suficiente."
            unlock="Se habilita cuando una divergencia supera los umbrales documentados."
            compact
          />
        )}
      </Section>

      <Section eyebrow="PERCEPTION · SEPARADA DEL SCORE" title="Data, expertos y fans">
        <div className="perception-columns">
          {(["media", "expert", "fan"] as const).map((kind) => {
            const items = perception.filter((item) => item.sourceKind === kind);
            return (
              <div key={kind}>
                <h3>{kind === "media" ? "DATA / MEDIA" : kind === "expert" ? "EXPERTOS" : "FANS"}</h3>
                {items.length ? (
                  items.map((item) => <PerceptionEvidenceCard evidence={item} key={item.evidenceId} />)
                ) : (
                  <EmptyState
                    title={`Sin evidencia de ${kind}`}
                    missing="No hay fuentes vinculadas de forma inequívoca a este jugador."
                    unlock="La percepción aparece aquí y nunca modifica el score objetivo."
                    compact
                  />
                )}
              </div>
            );
          })}
        </div>
      </Section>

      <p className="ranking-summary">
        <Link href={`/rankings?context=${contextQuery}`}>Volver a jugadores →</Link> ·{" "}
        <Link href={`/compare?type=player&context=${contextQuery}&left=${playerId}`}>
          Comparar este jugador →
        </Link>{" "}
        · fuente/contexto: {data.context.scopeKey} · {data.context.modelVersion}
      </p>
    </main>
  );
}
