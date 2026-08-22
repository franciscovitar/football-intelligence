import type { Metadata } from "next";
import { connection } from "next/server";

import { ComparisonRow, EmptyState, MetricComparisonRow, Section } from "@/features/product/product-ui";
import { selectPlayerContext } from "@/lib/player-context";
import { PLAYER_DIMENSION_LABELS, TEAM_DIMENSION_LABELS, humanMetric } from "@/lib/product-display";
import { getCompareOptions, getProductTeamDetail, type CompareOption } from "@/lib/queries/product-intelligence";
import {
  getScopedPlayerCompareOptions,
  getScopedPlayerContexts,
  getScopedPlayerDetail,
} from "@/lib/queries/scoped-player-intelligence";

import { resolveCompareType } from "./compare-type";

export const metadata: Metadata = { title: "Comparar V2" };
const value = (input: string | string[] | undefined) => Array.isArray(input) ? (input[0] ?? "") : (input ?? "");

export default async function ComparePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await connection();
  const params = await searchParams;
  const type = resolveCompareType(value(params.type));
  const leftId = Number(value(params.left));
  const rightId = Number(value(params.right));

  const contextsResult = type === "player" ? await getScopedPlayerContexts() : null;
  const contexts = contextsResult?.status === "ready" ? contextsResult.data : [];
  const selectedContext = type === "player" ? selectPlayerContext(contexts, value(params.context)) : null;
  const contextScopeKey = selectedContext?.scopeKey ?? (value(params.context) || "invalid");

  let options: CompareOption[] = [];
  if (type === "player") {
    const playerOptionsResult = await getScopedPlayerCompareOptions(contextScopeKey);
    if (playerOptionsResult.status === "ready") options = playerOptionsResult.data;
  } else {
    const teamOptionsResult = await getCompareOptions();
    if (teamOptionsResult.status === "ready") options = teamOptionsResult.data.teams;
  }

  const detailsPromise = leftId > 0 && rightId > 0
    ? type === "player"
      ? Promise.all([
          getScopedPlayerDetail(leftId, contextScopeKey),
          getScopedPlayerDetail(rightId, contextScopeKey),
        ])
      : Promise.all([getProductTeamDetail(leftId), getProductTeamDetail(rightId)])
    : Promise.resolve([null, null] as const);
  const [leftResult, rightResult] = await detailsPromise;
  const left = leftResult?.status === "ready" ? leftResult.data : null;
  const right = rightResult?.status === "ready" ? rightResult.data : null;
  const leftWindow = left?.windows.find((item) => item.window === "season") ?? left?.windows[0];
  const rightWindow = right?.windows.find((item) => item.window === "season") ?? right?.windows[0];
  const labels = type === "player" ? PLAYER_DIMENSION_LABELS : TEAM_DIMENSION_LABELS;
  const dimensionNames = leftWindow && rightWindow ? Array.from(new Set([...Object.keys(leftWindow.dimensions), ...Object.keys(rightWindow.dimensions)])) : [];
  const leftMetrics = leftWindow && left ? left.metrics[leftWindow.window] : [];
  const rightMetrics = rightWindow && right ? right.metrics[rightWindow.window] : [];
  const metricNames = Array.from(new Set([...leftMetrics.map((item) => item.metricName), ...rightMetrics.map((item) => item.metricName)])).slice(0, 20);

  return <main className="page-shell"><section className="page-heading"><div><p className="eyebrow">COMPARE · V2 {type === "player" && selectedContext?.isHistorical ? "· HISTÓRICO" : ""}</p><h1>{type === "player" ? "Jugador vs jugador" : "Equipo vs equipo"}</h1><p>Comparación lado a lado dentro del mismo tipo y, para jugadores, del mismo contexto de competición y temporada. Los huecos siguen siendo inconclusos, nunca cero.</p></div></section>
    <form className="filters compare-filters" method="get"><label><span>Tipo</span><select defaultValue={type} name="type"><option value="player">Jugadores</option><option value="team">Equipos</option></select></label>{type === "player" ? <label><span>Contexto</span><select defaultValue={selectedContext?.scopeKey ?? ""} name="context" required><option disabled value="">Elegir contexto</option>{contexts.map((item) => <option key={item.scopeKey} value={item.scopeKey}>{item.competitionName} · {item.seasonLabel}{item.isHistorical ? " · Histórico" : ""}</option>)}</select></label> : null}<label><span>Izquierda</span><select defaultValue={leftId || ""} name="left"><option value="">Elegir</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.subtitle}</option>)}</select></label><label><span>Derecha</span><select defaultValue={rightId || ""} name="right"><option value="">Elegir</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.subtitle}</option>)}</select></label><button className="button button-primary filter-button" type="submit">Comparar</button></form>
    {type === "player" && contextsResult?.status !== "ready" ? <EmptyState title="No pudimos leer los contextos de jugadores" missing={contextsResult?.message ?? "Contexto no disponible"} unlock="Revisá la conexión del snapshot real V2." /> : type === "player" && !selectedContext ? <EmptyState title="Contexto de jugadores no disponible" missing="No existe una temporada Player V2 válida para comparar." unlock="Elegí un contexto histórico publicado antes de seleccionar jugadores." /> : !left || !right || !leftWindow || !rightWindow ? <EmptyState title="Elegí dos entidades comparables" missing={options.length ? "Falta una selección válida con detalle real V2 en ambos lados." : "No hay dos entidades reales V2 disponibles en este contexto."} unlock="La comparación no mezcla temporadas, jugadores con equipos ni perfiles V1." /> : <>
      <section className="compare-identities"><article><span>A</span><h2>{"player" in left ? left.player.playerName : left.team.teamName}</h2><p>{"player" in left ? `${left.player.teamName ?? "Sin equipo"} · ${left.player.competitionName ?? "Sin liga"} · ${left.player.seasonLabel ?? "Sin temporada"}` : `${left.context.competitionName ?? "Sin liga"}`} · {"minutes" in leftWindow ? `${leftWindow.minutes} min` : `${leftWindow.matches} PJ`}</p></article><article><span>B</span><h2>{"player" in right ? right.player.playerName : right.team.teamName}</h2><p>{"player" in right ? `${right.player.teamName ?? "Sin equipo"} · ${right.player.competitionName ?? "Sin liga"} · ${right.player.seasonLabel ?? "Sin temporada"}` : `${right.context.competitionName ?? "Sin liga"}`} · {"minutes" in rightWindow ? `${rightWindow.minutes} min` : `${rightWindow.matches} PJ`}</p></article></section>
      <Section eyebrow="OVERALL" title="Score y evidencia"><ComparisonRow label={`Confianza ${Math.round(leftWindow.confidence * 100)}% / ${Math.round(rightWindow.confidence * 100)}%`} left={leftWindow.evidenceState === "ready" ? leftWindow.overallScore : null} right={rightWindow.evidenceState === "ready" ? rightWindow.overallScore : null} /></Section>
      <Section eyebrow="DIMENSIONS" title="Dónde está la diferencia"><div className="comparison-list">{dimensionNames.map((dimension) => { const leftEvidence = leftWindow.dimensions[dimension]; const rightEvidence = rightWindow.dimensions[dimension]; return <ComparisonRow key={dimension} label={(labels as Record<string, string>)[dimension] ?? dimension.replaceAll("_", " ")} left={leftEvidence?.evidenceState === "ready" ? leftEvidence.score : null} right={rightEvidence?.evidenceState === "ready" ? rightEvidence.score : null} />; })}</div></Section>
      <Section eyebrow="DIRECT EVIDENCE" title="Métricas y percentiles lado a lado">{metricNames.length ? <div className="comparison-list">{metricNames.map((metricName) => <MetricComparisonRow key={metricName} label={humanMetric(metricName)} left={leftMetrics.find((item) => item.metricName === metricName)} right={rightMetrics.find((item) => item.metricName === metricName)} />)}</div> : <EmptyState title="Métricas directas no disponibles" missing="Los perfiles no comparten features publicables en esta ventana." unlock="La comparación se habilita sin convertir valores ni percentiles ausentes en cero." compact />}</Section>
      <div className="comparison-caveat"><strong>Lectura de poblaciones</strong><p>{type === "player" ? `Ambos jugadores pertenecen al mismo contexto ${selectedContext?.competitionName ?? ""} ${selectedContext?.seasonLabel ?? ""}; una dimensión parcial se mantiene inconclusa.` : left.context.competitionCode && right.context.competitionCode && left.context.competitionCode !== right.context.competitionCode ? "Las ligas difieren y no existe todavía un ajuste de fuerza entre competiciones. Los percentiles no implican igualdad directa." : "La comparación usa las poblaciones declaradas por cada feature; una dimensión parcial se mantiene inconclusa."}</p></div>
    </>}
  </main>;
}
