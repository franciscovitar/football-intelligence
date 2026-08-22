import Link from "next/link";
import { connection } from "next/server";

import { EmptyState, PlayerProductCard, Section, TeamProductCard } from "@/features/product/product-ui";
import { getProductHome, getProductTeamDirectory } from "@/lib/queries/product-intelligence";
import { getScopedPlayerContexts } from "@/lib/queries/scoped-player-intelligence";

const EMPTY = {
  players: {
    missing: "No hay jugadores del contexto principal que superen a la vez los controles de muestra, evidencia y confianza.",
    unlock: "Los contextos históricos se exploran por separado para no mezclarlos con la última temporada completa.",
  },
  perception: {
    missing: "No existe evidencia objetiva y de percepción comparable en una escala normalizada.",
    unlock: "Se habilita cuando ambos datasets tienen cobertura y confianza suficientes.",
  },
};

export default async function HomePage() {
  await connection();
  const [result, teamDirectoryResult, playerContextsResult] = await Promise.all([
    getProductHome(),
    getProductTeamDirectory(),
    getScopedPlayerContexts(),
  ]);
  const data = result.status === "ready" ? result.data : null;
  const teamContext = teamDirectoryResult.status === "ready" ? teamDirectoryResult.data.context : null;
  const playerContexts = playerContextsResult.status === "ready" ? playerContextsResult.data : [];
  const historicalPlayerContext = playerContexts.find((item) => item.isHistorical) ?? null;
  const historicalPlayerHref = historicalPlayerContext
    ? `/rankings?context=${encodeURIComponent(historicalPlayerContext.scopeKey)}`
    : "/rankings";

  return (
    <main className="page-shell">
      <section className="hero product-hero">
        <div>
          <p className="eyebrow">FOOTBALL INTELLIGENCE · ÚLTIMA TEMPORADA COMPLETA</p>
          <h1>Entendé el partido largo.</h1>
          <p className="hero-copy">Una lectura rápida de rendimiento, proceso y evidencia real. Cada score publica su muestra, confianza y límites.</p>
          <div className="hero-actions"><Link className="button button-primary" href="/team-rankings">Explorar equipos</Link><Link className="button button-secondary" href="/compare">Comparar equipos</Link></div>
          <small><Link href={historicalPlayerHref}>{historicalPlayerContext ? `Explorar jugadores históricos · ${historicalPlayerContext.seasonLabel} →` : "Jugadores históricos todavía no publicados →"}</Link></small>
        </div>
        <div className="briefing-card"><span>Estado de datos</span><strong>{teamContext ? "Snapshot V2 real de equipos activo" : "Cobertura real insuficiente"}</strong><p>{teamContext ? `${teamContext.competitionName ?? teamContext.competitionCode ?? "Competición"} · ${teamContext.seasonLabel ?? "temporada"} · ${teamContext.modelVersion}` : "La experiencia permanece útil y explica qué falta; nunca completa huecos con datos de prueba."}</p><Link href="/sources">Ver cobertura y fuentes →</Link></div>
      </section>

      <div className="product-dashboard-grid">
        <Section eyebrow="TEAMS" title={data?.bestTeams.length ? "Mejores equipos" : "Equipos analizados"} action={<Link href="/team-rankings">{data?.bestTeams.length ? "Ranking completo" : "Explorar equipos"}</Link>}>
          {data?.bestTeams.length ? data.bestTeams.map((team, index) => <TeamProductCard key={team.teamId} team={team} rank={index + 1} />) : <EmptyState title="Ranking no disponible todavía" missing="El ranking todavía no es publicable, pero hay evidencia real disponible para los 20 equipos." unlock="Explorá el análisis por equipo: dimensiones, métricas y diagnósticos reales." compact />}
        </Section>
        <Section eyebrow="PLAYERS" title={data?.bestPlayers.length ? "Mejores jugadores" : historicalPlayerContext ? "Jugadores históricos" : "Jugadores"} action={<Link href={historicalPlayerHref}>{historicalPlayerContext ? "Explorar fichas" : "Ver estado"}</Link>}>
          {data?.bestPlayers.length ? data.bestPlayers.map((player, index) => <PlayerProductCard key={player.playerId} player={player} rank={index + 1} prominent />) : historicalPlayerContext ? <EmptyState title="Ranking overall no disponible" missing={`Hay fichas reales de ${historicalPlayerContext.competitionName} ${historicalPlayerContext.seasonLabel}, pero la evidencia no alcanza para ordenar jugadores con un overall defendible.`} unlock="Podés explorar jugadores, métricas y evidencia histórica sin convertir huecos en scores." compact /> : <EmptyState title="Sin contexto de jugadores publicado" {...EMPTY.players} compact />}
        </Section>
      </div>

      <div className="product-dashboard-grid">
        <Section eyebrow="FORM" title="Forma reciente">{data?.formPlayers.length ? data.formPlayers.map((player, index) => <PlayerProductCard key={player.playerId} player={player} rank={index + 1} />) : <EmptyState title="Sin ventana reciente comparable" missing="No hay una muestra real elegible de últimos cinco partidos para el contexto principal." unlock="Los datos históricos no se mezclan automáticamente con la lectura de la última temporada completa." compact />}</Section>
        <Section eyebrow="NOW" title="Señales importantes">{data?.nowSignals.length ? <div className="signal-list">{data.nowSignals.map((signal) => <Link href={`/${signal.entityType}/${signal.entityId}`} key={`${signal.entityType}-${signal.entityId}-${signal.diagnosticCode}`}><strong>{signal.entityName}</strong><span>{signal.diagnosticCode.replaceAll("_", " ")} · conf. {Math.round(signal.confidence * 100)}%</span></Link>)}</div> : <EmptyState title="Sin señales publicables" missing="Los diagnósticos actuales no están respaldados por una entidad real V2 elegible." unlock="Se habilita cuando proceso y resultado pueden compararse con evidencia suficiente." compact />}</Section>
      </div>

      <div className="product-dashboard-grid">
        <Section eyebrow="SURPRISES" title="Sorpresas y decepciones">{data && (data.surprises.length || data.disappointments.length) ? <div className="signal-list">{[...data.surprises, ...data.disappointments].map((signal) => <Link href={`/player/${signal.entityId}`} key={`${signal.entityId}-${signal.diagnosticCode}`}><strong>{signal.entityName}</strong><span>{signal.diagnosticCode.replaceAll("_", " ")}</span></Link>)}</div> : <EmptyState title="Sin divergencias verificables" missing="No hay resultados y proceso subyacente suficientes para clasificar sorpresas o decepciones." unlock="Se habilita con output real y métricas esperadas comparables." compact />}</Section>
        <Section eyebrow="WATCHLIST" title="Para seguir" action={<Link href="/watchlist">Abrir watchlist</Link>}>{data?.watchlist.length ? <div className="signal-list">{data.watchlist.map((player) => <Link href={`/player/${player.playerId}`} key={player.playerId}><strong>{player.playerName}</strong><span>{player.reason ?? player.category.replaceAll("_", " ")}</span></Link>)}</div> : <EmptyState title="Watchlist vacía" missing="No agregaste jugadores y no hay sugerencias automáticas con evidencia V2 suficiente." unlock="La watchlist del contexto principal no incorpora temporadas históricas automáticamente." compact />}</Section>
      </div>

      <div className="product-dashboard-grid">
        <Section eyebrow="PERCEPTION" title="Infravalorados / sobrevalorados"><EmptyState title="Comparación no disponible" {...EMPTY.perception} compact /></Section>
        <Section eyebrow="RESULTS VS PERFORMANCE" title="Resultado y proceso" action={<Link href="/results-vs-performance">Explorar divergencias</Link>}><EmptyState title="Lectura honesta, sin atajos" missing="Esta sección solo muestra conclusiones cuando resultado y proceso subyacente tienen respaldo real." unlock="Describimos la divergencia sin atribuir causalidad ni rellenar output esperado ausente." compact /></Section>
      </div>

      <Section eyebrow="TEAM INTELLIGENCE" title="Qué pasa con los equipos">{data?.teamSignals.length ? <div className="signal-list">{data.teamSignals.map((signal) => <Link href={`/team/${signal.entityId}`} key={`${signal.entityId}-${signal.diagnosticCode}`}><strong>{signal.entityName}</strong><span>{signal.diagnosticCode.replaceAll("_", " ")}</span></Link>)}</div> : <EmptyState title="Sin diagnósticos de equipo elegibles" missing="No hay una señal real V2 que supere los controles actuales." unlock="Se habilita al completar métricas de creación, control y proceso defensivo." compact />}</Section>
    </main>
  );
}
