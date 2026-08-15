import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { Confidence, DimensionCard, EmptyState, EvidenceBadge, MetricRow, ScoreBadge, Section } from "@/features/product/product-ui";
import { TEAM_DIMENSION_LABELS, WINDOW_LABELS, humanMetric } from "@/lib/product-display";
import { TEAM_RANKING_DIMENSIONS, getProductTeamDetail } from "@/lib/queries/product-intelligence";

export const metadata: Metadata = { title: "Equipo V2" };

export default async function TeamPage({ params }: { params: Promise<{ id: string }> }) {
  await connection(); const { id } = await params; const teamId = Number(id); if (!Number.isInteger(teamId) || teamId < 1) notFound();
  const result = await getProductTeamDetail(teamId); if (result.status === "ready" && result.data === null) notFound();
  if (result.status !== "ready") return <main className="page-shell"><EmptyState title="Equipo V2 no disponible" missing={result.message} unlock="No se usa el perfil V1 como reemplazo de un snapshot V2 ausente." /></main>;
  const data = result.data; if (data === null) notFound(); const season = data.windows.find((item) => item.window === "season") ?? data.windows[0]; if (!season) notFound(); const metrics = data.metrics[season.window];
  return <main className="page-shell"><section className="player-hero product-detail-hero"><div><p className="eyebrow">TEAM INTELLIGENCE · V2 REAL</p><h1>{data.team.teamName}</h1><p>{data.context.competitionName ?? "Competición no disponible"} · {data.context.seasonLabel ?? "Temporada no disponible"} · {season.matches} PJ</p></div><div><ScoreBadge score={season.overallScore} state={season.evidenceState} /><Confidence value={season.confidence} coverage={season.evidenceCoveragePct} /></div></section>
    <Section eyebrow="PRIMARY VERDICT" title="Rendimiento del equipo"><div className="verdict-copy"><EvidenceBadge state={season.evidenceState} /><p>{season.evidenceState === "ready" ? "El score V2 está respaldado por cobertura y confianza suficientes." : "El equipo real se muestra, pero no entra en rankings hasta completar su evidencia."}</p></div></Section>
    <Section eyebrow="RESULTS VS PROCESS" title="Resultado y proceso subyacente"><EmptyState title="Divergencia no disponible" missing="El snapshot Team V2 no expone todavía un par comparable de puntos esperados y resultados." unlock="Se mostrará cuando ambos lados tengan la misma ventana y provenance real." compact /></Section>
    <Section eyebrow="DIMENSIONS" title="Perfil de equipo V2"><div className="dimension-card-grid">{TEAM_RANKING_DIMENSIONS.filter((item) => item !== "overall").map((dimension) => <DimensionCard key={dimension} label={TEAM_DIMENSION_LABELS[dimension]} evidence={season.dimensions[dimension]} />)}</div></Section>
    <Section eyebrow="WINDOWS" title="Ventanas disponibles"><div className="window-grid">{data.windows.map((item) => <article className="window-card" key={item.window}><span>{WINDOW_LABELS[item.window]}</span><strong>{item.overallScore === null ? "—" : Math.round(item.overallScore)}</strong><EvidenceBadge state={item.evidenceState} /><small>{item.matches} PJ · conf. {Math.round(item.confidence * 100)}%</small></article>)}</div></Section>
    <Section eyebrow="SUPPORTING METRICS" title="Evidencia observada">{metrics.length ? <div className="metric-category"><h3>Temporada</h3>{metrics.map((metric) => <MetricRow key={metric.metricName} metric={metric} />)}</div> : <EmptyState title="Sin métricas vinculadas" missing="No hay features reales de equipo para esta ventana." unlock="La fuente debe aportar métricas observadas; las ausentes no se transforman en cero." compact />}</Section>
    <Section eyebrow="DIAGNOSTICS" title="Qué merece atención">{season.diagnostics.length ? <div className="signal-list">{season.diagnostics.map((signal) => <article key={signal}><strong>{humanMetric(signal)}</strong><span>Regla determinista · {WINDOW_LABELS[season.window]}</span></article>)}</div> : <EmptyState title="Sin diagnóstico V2" missing="Ninguna regla respaldada por este snapshot produjo una señal." unlock="Se habilita con dimensiones y métricas suficientes." compact />}</Section>
    <Section eyebrow="TACTICAL INTELLIGENCE" title="Observado, estimado y no disponible"><div className="tactical-status-grid"><article><EvidenceBadge state="ready" /><h3>Observado</h3><p>Volumen, control y eventos presentes en las métricas fuente.</p></article><article><EvidenceBadge state="partial" /><h3>Estimado</h3><p>Solo inferencias ya calculadas por Tactical Intelligence; no se mezclan con el score V2.</p></article><article><EvidenceBadge state="insufficient_data" /><h3>No disponible</h3><p>Movimiento, marcajes, bloque y estrategia sin tracking o evidencia correspondiente.</p></article></div></Section>
    <p className="ranking-summary"><Link href="/compare">Comparar este equipo →</Link> · {data.context.scopeKey} · {data.context.modelVersion}</p>
  </main>;
}
