import type { Metadata } from "next";
import { connection } from "next/server";

import { ComparisonRow, EmptyState, MetricComparisonRow, Section } from "@/features/product/product-ui";
import { PLAYER_DIMENSION_LABELS, TEAM_DIMENSION_LABELS, humanMetric } from "@/lib/product-display";
import { getCompareOptions, getProductPlayerDetail, getProductTeamDetail } from "@/lib/queries/product-intelligence";

import { resolveCompareType } from "./compare-type";

export const metadata: Metadata = { title: "Comparar V2" };
const value = (input: string | string[] | undefined) => Array.isArray(input) ? (input[0] ?? "") : (input ?? "");

export default async function ComparePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await connection(); const params = await searchParams; const type = resolveCompareType(value(params.type)); const leftId = Number(value(params.left)); const rightId = Number(value(params.right));
  const detailsPromise = leftId > 0 && rightId > 0 ? type === "player" ? Promise.all([getProductPlayerDetail(leftId), getProductPlayerDetail(rightId)]) : Promise.all([getProductTeamDetail(leftId), getProductTeamDetail(rightId)]) : Promise.resolve([null, null] as const);
  const [optionsResult, [leftResult, rightResult]] = await Promise.all([getCompareOptions(), detailsPromise]);
  const options = optionsResult.status === "ready" ? (type === "player" ? optionsResult.data.players : optionsResult.data.teams) : [];
  const left = leftResult?.status === "ready" ? leftResult.data : null; const right = rightResult?.status === "ready" ? rightResult.data : null;
  const leftWindow = left?.windows.find((item) => item.window === "season") ?? left?.windows[0]; const rightWindow = right?.windows.find((item) => item.window === "season") ?? right?.windows[0];
  const labels = type === "player" ? PLAYER_DIMENSION_LABELS : TEAM_DIMENSION_LABELS;
  const dimensionNames = leftWindow && rightWindow ? Array.from(new Set([...Object.keys(leftWindow.dimensions), ...Object.keys(rightWindow.dimensions)])) : [];
  const leftMetrics = leftWindow && left ? left.metrics[leftWindow.window] : [];
  const rightMetrics = rightWindow && right ? right.metrics[rightWindow.window] : [];
  const metricNames = Array.from(new Set([...leftMetrics.map((item) => item.metricName), ...rightMetrics.map((item) => item.metricName)])).slice(0, 20);

  return <main className="page-shell"><section className="page-heading"><div><p className="eyebrow">COMPARE · V2</p><h1>{type === "player" ? "Jugador vs jugador" : "Equipo vs equipo"}</h1><p>Comparación lado a lado dentro del mismo tipo de entidad. Los huecos siguen siendo inconclusos, nunca cero.</p></div></section>
    <form className="filters compare-filters" method="get"><label><span>Tipo</span><select defaultValue={type} name="type"><option value="player">Jugadores</option><option value="team">Equipos</option></select></label><label><span>Izquierda</span><select defaultValue={leftId || ""} name="left"><option value="">Elegir</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.subtitle}</option>)}</select></label><label><span>Derecha</span><select defaultValue={rightId || ""} name="right"><option value="">Elegir</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.subtitle}</option>)}</select></label><button className="button button-primary filter-button" type="submit">Comparar</button></form>
    {!left || !right || !leftWindow || !rightWindow ? <EmptyState title="Elegí dos entidades comparables" missing={options.length ? "Falta una selección válida con detalle real V2 en ambos lados." : "No hay dos entidades reales V2 disponibles en este snapshot."} unlock="La comparación no mezcla jugadores con equipos ni recurre a perfiles V1." /> : <>
      <section className="compare-identities"><article><span>A</span><h2>{"player" in left ? left.player.playerName : left.team.teamName}</h2><p>{"player" in left ? `${left.player.teamName ?? "Sin equipo"} · ${left.player.competitionName ?? "Sin liga"}` : `${left.context.competitionName ?? "Sin liga"}`} · {"minutes" in leftWindow ? `${leftWindow.minutes} min` : `${leftWindow.matches} PJ`}</p></article><article><span>B</span><h2>{"player" in right ? right.player.playerName : right.team.teamName}</h2><p>{"player" in right ? `${right.player.teamName ?? "Sin equipo"} · ${right.player.competitionName ?? "Sin liga"}` : `${right.context.competitionName ?? "Sin liga"}`} · {"minutes" in rightWindow ? `${rightWindow.minutes} min` : `${rightWindow.matches} PJ`}</p></article></section>
      <Section eyebrow="OVERALL" title="Score y evidencia"><ComparisonRow label={`Confianza ${Math.round(leftWindow.confidence * 100)}% / ${Math.round(rightWindow.confidence * 100)}%`} left={leftWindow.evidenceState === "ready" ? leftWindow.overallScore : null} right={rightWindow.evidenceState === "ready" ? rightWindow.overallScore : null} /></Section>
      <Section eyebrow="DIMENSIONS" title="Dónde está la diferencia"><div className="comparison-list">{dimensionNames.map((dimension) => { const leftEvidence = leftWindow.dimensions[dimension]; const rightEvidence = rightWindow.dimensions[dimension]; return <ComparisonRow key={dimension} label={(labels as Record<string, string>)[dimension] ?? dimension.replaceAll("_", " ")} left={leftEvidence?.evidenceState === "ready" ? leftEvidence.score : null} right={rightEvidence?.evidenceState === "ready" ? rightEvidence.score : null} />; })}</div></Section>
      <Section eyebrow="DIRECT EVIDENCE" title="Métricas y percentiles lado a lado">{metricNames.length ? <div className="comparison-list">{metricNames.map((metricName) => <MetricComparisonRow key={metricName} label={humanMetric(metricName)} left={leftMetrics.find((item) => item.metricName === metricName)} right={rightMetrics.find((item) => item.metricName === metricName)} />)}</div> : <EmptyState title="Métricas directas no disponibles" missing="Los perfiles no comparten features publicables en esta ventana." unlock="La comparación se habilita sin convertir valores ni percentiles ausentes en cero." compact />}</Section>
      <div className="comparison-caveat"><strong>Lectura de poblaciones</strong><p>{left.context.competitionCode && right.context.competitionCode && left.context.competitionCode !== right.context.competitionCode ? "Las ligas difieren y no existe todavía un ajuste de fuerza entre competiciones. Los percentiles no implican igualdad directa." : "La comparación usa las poblaciones declaradas por cada feature; una dimensión parcial se mantiene inconclusa."}</p></div>
    </>}
  </main>;
}
