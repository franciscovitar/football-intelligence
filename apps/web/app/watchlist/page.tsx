import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { EmptyState, EvidenceBadge, Section } from "@/features/product/product-ui";
import { isWriteAuthConfigured } from "@/lib/auth/write-guard";
import { isWriteAuthorized } from "@/lib/auth/write-session";
import { formatScore, humanMetric } from "@/lib/product-display";
import { getProductTeamDirectory, getWatchlistData } from "@/lib/queries/product-intelligence";
import { getScopedPlayerContexts } from "@/lib/queries/scoped-player-intelligence";

import { addWatchlistEntry, removeWatchlistEntry } from "./actions";
import { authorizeWrites, deauthorizeWrites } from "./auth-actions";

export const metadata: Metadata = { title: "Watchlist" };
export default async function WatchlistPage() {
  await connection();
  const [result, teamResult, playerContextsResult] = await Promise.all([
    getWatchlistData(),
    getProductTeamDirectory(),
    getScopedPlayerContexts(),
  ]);
  const data = result.status === "ready" ? result.data : null;
  const teamContext = teamResult.status === "ready" ? teamResult.data.context : null;
  const playerContexts = playerContextsResult.status === "ready" ? playerContextsResult.data : [];
  const primaryPlayerContext = teamContext
    ? playerContexts.find((context) => context.scopeKey === teamContext.scopeKey) ?? null
    : null;
  const candidates = primaryPlayerContext ? (data?.candidates ?? []) : [];
  const entries = primaryPlayerContext ? (data?.entries ?? []) : [];
  const automaticSuggestions = primaryPlayerContext ? (data?.automaticSuggestions ?? []) : [];
  const writeConfigured = isWriteAuthConfigured();
  const writeAuthorized = writeConfigured && (await isWriteAuthorized());

  return <main className="page-shell"><section className="page-heading"><div><p className="eyebrow">PERSISTENT WATCHLIST</p><h1>Lo que vale la pena seguir.</h1><p>Una lista personal ligada al contexto principal del producto. Las temporadas históricas se exploran por separado y no entran automáticamente acá.</p></div></section>
    <Section eyebrow="ADD" title="Agregar jugador real V2" action={writeAuthorized ? <form action={deauthorizeWrites}><button className="button button-secondary" type="submit">Cerrar sesión de escritura</button></form> : undefined}>{!primaryPlayerContext ? <EmptyState title="Sin jugadores del contexto principal" missing="Hay evidencia histórica disponible, pero todavía no existe Player V2 para la misma temporada que usa la experiencia principal de equipos." unlock="Explorá los jugadores históricos desde Jugadores; la watchlist no mezcla temporadas automáticamente." compact /> : !writeConfigured ? <EmptyState title="Escritura deshabilitada" missing="No hay un token de escritura configurado en el servidor." unlock="Configurá FOOTBALL_INTELLIGENCE_WRITE_TOKEN para habilitar altas y bajas; la lectura sigue pública." compact /> : !writeAuthorized ? <form action={authorizeWrites} className="watchlist-form"><label className="search-field"><span>Token de escritura</span><input autoComplete="off" name="token" required type="password" /></label><button className="button button-primary" type="submit">Desbloquear escritura</button></form> : candidates.length ? <form action={addWatchlistEntry} className="watchlist-form"><label><span>Jugador</span><select name="playerId" required>{candidates.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.subtitle}</option>)}</select></label><label><span>Categoría</span><select name="category"><option value="manual">Manual</option><option value="emerging">Emerging</option><option value="regression_watch">Regression watch</option><option value="underperforming_process">Strong process / weak output</option></select></label><label className="search-field"><span>Nota opcional</span><input maxLength={500} name="reason" /></label><button className="button button-primary" type="submit">Agregar</button></form> : <EmptyState title="Sin candidatos reales V2" missing="No existe un jugador real elegible que todavía no esté en la lista." unlock="Las entidades test/synthetic quedan excluidas por el contrato de lectura." compact />}</Section>
    <Section eyebrow="CURRENT" title="Tu lista">{entries.length ? <div className="watchlist-grid">{entries.map((entry) => <article key={entry.playerId}><div><span>{humanMetric(entry.category)}</span><h3><Link href={`/player/${entry.playerId}?context=${encodeURIComponent(primaryPlayerContext?.scopeKey ?? "")}`}>{entry.playerName}</Link></h3><p>{entry.teamName ?? "Equipo no disponible"}</p></div><div><strong>{formatScore(entry.score)}</strong><EvidenceBadge state={entry.evidenceState} /><small>conf. {Math.round(entry.confidence * 100)}%</small></div>{entry.reason ? <p>{entry.reason}</p> : null}{writeAuthorized ? <form action={removeWatchlistEntry}><input name="playerId" type="hidden" value={entry.playerId} /><button className="button button-secondary" type="submit">Quitar</button></form> : null}</article>)}</div> : <EmptyState title="Watchlist vacía" missing="Todavía no hay jugadores del contexto principal guardados." unlock="Las fichas históricas no se agregan automáticamente a esta lista." compact />}</Section>
    <Section eyebrow="AUTOMATIC SUGGESTIONS" title="Señales para revisar">{automaticSuggestions.length ? <div className="signal-list">{automaticSuggestions.map((item) => <Link href={`/player/${item.entityId}?context=${encodeURIComponent(primaryPlayerContext?.scopeKey ?? "")}`} key={`${item.entityId}-${item.diagnosticCode}`}><strong>{item.entityName}</strong><span>{humanMetric(item.diagnosticCode)} · conf. {Math.round(item.confidence * 100)}%</span></Link>)}</div> : <EmptyState title="Sin sugerencias automáticas" missing="Ninguna señal del contexto principal supera hoy los controles deterministas." unlock="No se agregan históricos, famosos ni entradas de prueba por defecto." compact />}</Section>
  </main>;
}
