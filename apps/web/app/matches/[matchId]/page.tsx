import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import {
  getMatchDetail,
  type MatchPlayerReview,
  type MatchStatLine,
  type MatchTeamReview,
} from "@/lib/queries/match-detail";

export const metadata: Metadata = { title: "Partido" };

const scoreText = (value: number | null): string => (value === null ? "—" : value.toFixed(1));
const statText = (value: number | null, suffix = ""): string =>
  value === null ? "—" : `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}${suffix}`;

function ratingClass(score: number): string {
  if (score >= 9) return "match-rating match-rating--world";
  if (score >= 8) return "match-rating match-rating--excellent";
  if (score >= 7) return "match-rating match-rating--good";
  if (score >= 6) return "match-rating match-rating--solid";
  if (score >= 5) return "match-rating match-rating--weak";
  return "match-rating match-rating--poor";
}

function Confidence({ value }: { value: number }) {
  return (
    <span className="match-confidence" title={`Confianza ${value}/100`}>
      <span className="match-confidence-track" aria-hidden="true">
        <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
      <small>{value}</small>
    </span>
  );
}

function ChannelScores({ facts, expert, fan }: { facts: number | null; expert: number | null; fan: number | null }) {
  return (
    <div className="match-channels" aria-label="Canales de evidencia">
      <span><small>Facts</small><strong>{scoreText(facts)}</strong></span>
      <span><small>Expertos</small><strong>{scoreText(expert)}</strong></span>
      <span><small>Hinchas</small><strong>{scoreText(fan)}</strong></span>
    </div>
  );
}

function StatComparison({ label, home, away, suffix = "" }: { label: string; home: number | null; away: number | null; suffix?: string }) {
  const total = Math.max(0, (home ?? 0) + (away ?? 0));
  const homeShare = total > 0 ? ((home ?? 0) / total) * 100 : 50;
  return (
    <div className="match-stat-row">
      <strong>{statText(home, suffix)}</strong>
      <div>
        <span>{label}</span>
        <span className="match-stat-track" aria-hidden="true"><i style={{ width: `${homeShare}%` }} /></span>
      </div>
      <strong>{statText(away, suffix)}</strong>
    </div>
  );
}

function getExtraNumber(stat: MatchStatLine | undefined, key: string): number | null {
  const value = stat?.extra[key];
  return typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : null;
}

const DIMENSIONS: Array<[keyof MatchTeamReview, string]> = [
  ["attackScore", "Ataque"],
  ["creationScore", "Creación"],
  ["controlScore", "Control"],
  ["defenceScore", "Defensa"],
  ["pressingScore", "Presión"],
  ["offensiveTransitionScore", "Transición +"],
  ["defensiveTransitionScore", "Transición −"],
];

function TeamVerdict({ review }: { review: MatchTeamReview }) {
  return (
    <article className="panel match-team-card">
      <div className="match-card-head">
        <div><p className="eyebrow">EQUIPO · FI MATCH</p><h2>{review.teamName}</h2></div>
        <div className={ratingClass(review.finalScore)}><strong>{review.finalScore.toFixed(1)}</strong><small>FI</small></div>
      </div>
      <ChannelScores facts={review.factsScore} expert={review.expertScore} fan={review.fanScore} />
      <div className="match-confidence-row"><span>Confianza de la conclusión</span><Confidence value={review.confidence} /></div>
      <p className="match-summary">{review.summary}</p>
      <div className="match-dimensions">
        {DIMENSIONS.map(([key, label]) => {
          const value = review[key];
          if (typeof value !== "number") return null;
          return <div key={key}><span>{label}</span><i><b style={{ width: `${value * 10}%` }} /></i><strong>{value.toFixed(1)}</strong></div>;
        })}
      </div>
      <div className="match-pros-cons">
        <div><span>Lo mejor</span>{review.strengths.map((item) => <p key={item}>+ {item}</p>)}</div>
        <div><span>Alertas</span>{review.concerns.map((item) => <p key={item}>− {item}</p>)}</div>
      </div>
    </article>
  );
}

function PlayerList({ teamId, teamName, players }: { teamId: string; teamName: string; players: MatchPlayerReview[] }) {
  const rows = players.filter((player) => player.teamId === teamId);
  return (
    <section className="panel match-player-panel">
      <div className="section-heading"><div><p className="eyebrow">PLAYER REVIEWS</p><h2>{teamName}</h2></div><p>{rows.length} jugadores evaluados</p></div>
      <div className="match-player-header" aria-hidden="true"><span>Jugador</span><span>Facts</span><span>Exp.</span><span>Fans</span><span>FI</span><span>Conf.</span></div>
      <div className="match-player-list">
        {rows.map((player) => (
          <details className="match-player" key={player.playerId}>
            <summary>
              <span className="match-player-name"><strong>{player.playerName}</strong><small>{player.starter ? "Titular" : "Suplente"} · {player.minutes ?? "—"}' · {player.roleLabel ?? "rol no especificado"}</small></span>
              <span>{scoreText(player.factsScore)}</span>
              <span>{scoreText(player.expertScore)}</span>
              <span>{scoreText(player.fanScore)}</span>
              <span className={ratingClass(player.finalScore)}><strong>{player.finalScore.toFixed(1)}</strong></span>
              <Confidence value={player.confidence} />
            </summary>
            <div className="match-player-detail">
              <p>{player.summary}</p>
              <div className="match-player-evidence">
                <span>Provider: {scoreText(player.providerRating)}</span>
                <span>G/A: {player.goals ?? "—"}/{player.assists ?? "—"}</span>
                <span>xG: {player.xg === null ? "—" : player.xg.toFixed(2)}</span>
                <span>Tiros: {player.shots ?? "—"} · a puerta {player.shotsOnTarget ?? "—"}</span>
                <span>{player.evidenceStatus}</span>
              </div>
              {(player.positiveNotes.length > 0 || player.negativeNotes.length > 0) && <div className="match-pros-cons compact">
                <div>{player.positiveNotes.map((item) => <p key={item}>+ {item}</p>)}</div>
                <div>{player.negativeNotes.map((item) => <p key={item}>− {item}</p>)}</div>
              </div>}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

export default async function MatchPage({ params }: { params: Promise<{ matchId: string }> }) {
  await connection();
  const { matchId } = await params;
  const result = await getMatchDetail(matchId);

  if (result.status === "ready" && !result.data) notFound();
  if (result.status !== "ready") {
    return <main className="page-shell"><section className="panel not-found"><p className="eyebrow">MATCH PAGE</p><h1>No disponible</h1><p>{result.message}</p></section></main>;
  }

  const match = result.data;
  const homeStats = match.stats.find((item) => item.teamId === match.home.id);
  const awayStats = match.stats.find((item) => item.teamId === match.away.id);
  const homeReview = match.teamReviews.find((item) => item.teamId === match.home.id);
  const awayReview = match.teamReviews.find((item) => item.teamId === match.away.id);
  const formattedDate = new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(match.kickoffAt));

  return (
    <main className="page-shell match-page">
      <section className="match-scoreboard">
        <p className="eyebrow">{match.competition} · {match.round ?? match.season} · {formattedDate}</p>
        <div className="match-scoreline">
          <div><span>{match.home.shortName ?? match.home.name}</span>{homeReview && <small>FI {homeReview.finalScore.toFixed(1)}</small>}</div>
          <strong>{match.homeGoals}<i>–</i>{match.awayGoals}</strong>
          <div><span>{match.away.shortName ?? match.away.name}</span>{awayReview && <small>FI {awayReview.finalScore.toFixed(1)}</small>}</div>
        </div>
        <p className="match-score-note">La nota FI evalúa la actuación, no sólo el resultado. Facts, expertos e hinchas son canales auditables; la síntesis no usa pesos fijos.</p>
      </section>

      <section className="context-strip match-context">
        <div><span>Estadio</span><strong>{match.venue ?? "—"}</strong></div>
        <div><span>Asistencia</span><strong>{match.attendance?.toLocaleString("es-AR") ?? "—"}</strong></div>
        <div><span>Árbitro</span><strong>{match.referee ?? "—"}</strong></div>
      </section>

      <section className="dashboard-grid match-top-grid">
        <article className="panel match-facts-panel">
          <div className="section-heading"><div><p className="eyebrow">FACTS</p><h2>Qué produjo el partido</h2></div><p>{homeStats?.providerName ?? awayStats?.providerName ?? "Fuente estructurada"}</p></div>
          <div className="match-stat-teams"><strong>{match.home.shortName ?? match.home.name}</strong><strong>{match.away.shortName ?? match.away.name}</strong></div>
          <StatComparison label="xG · calidad de ocasiones" home={homeStats?.xg ?? null} away={awayStats?.xg ?? null} />
          <StatComparison label="Tiros" home={homeStats?.shots ?? null} away={awayStats?.shots ?? null} />
          <StatComparison label="A puerta" home={homeStats?.shotsOnTarget ?? null} away={awayStats?.shotsOnTarget ?? null} />
          <StatComparison label="Posesión" home={homeStats?.possession ?? null} away={awayStats?.possession ?? null} suffix="%" />
          <StatComparison label="Toques en área" home={homeStats?.boxTouches ?? null} away={awayStats?.boxTouches ?? null} />
          <StatComparison label="xA · calidad creada para otros" home={getExtraNumber(homeStats, "xA")} away={getExtraNumber(awayStats, "xA")} />
          <p className="match-provider-note">El xG mostrado conserva el modelo del proveedor; no promediamos modelos incompatibles.</p>
        </article>

        <article className="panel match-reading">
          <div className="section-heading"><div><p className="eyebrow">LECTURA FI</p><h2>Qué cuenta el partido</h2></div></div>
          <p>{match.reading}</p>
          <div className="match-takeaways">{match.takeaways.map((item, index) => <div key={item}><span>{String(index + 1).padStart(2, "0")}</span><p>{item}</p></div>)}</div>
        </article>
      </section>

      {homeReview && awayReview && <section className="dashboard-grid match-team-grid"><TeamVerdict review={homeReview} /><TeamVerdict review={awayReview} /></section>}

      <section className="dashboard-grid match-manager-grid">
        {match.managerReviews.map((review) => (
          <article className="panel match-manager" key={review.managerId}>
            <div className="match-card-head"><div><p className="eyebrow">TÉCNICO · {review.teamName}</p><h2>{review.managerName}</h2></div><div className={ratingClass(review.finalScore)}><strong>{review.finalScore.toFixed(1)}</strong><small>FI</small></div></div>
            <ChannelScores facts={review.factsScore} expert={review.expertScore} fan={review.fanScore} />
            <div className="match-confidence-row"><span>Confianza</span><Confidence value={review.confidence} /></div>
            <p className="match-summary">{review.summary}</p>
            <div className="match-manager-scores">
              <span>Plan <strong>{scoreText(review.initialPlanScore)}</strong></span>
              <span>Adaptación <strong>{scoreText(review.adaptationScore)}</strong></span>
              <span>Cambios <strong>{scoreText(review.substitutionsScore)}</strong></span>
            </div>
            {review.initialPlan && <p><b>Plan:</b> {review.initialPlan}</p>}
            {review.adjustments && <p><b>Ajustes:</b> {review.adjustments}</p>}
          </article>
        ))}
      </section>

      <div className="match-player-columns">
        <PlayerList teamId={match.home.id} teamName={match.home.name} players={match.playerReviews} />
        <PlayerList teamId={match.away.id} teamName={match.away.name} players={match.playerReviews} />
      </div>

      <section className="panel match-sources">
        <details>
          <summary><span><b>Fuentes y evidencia</b><small>{match.sources.length} documentos públicos usados en la lectura general</small></span><strong>Ver</strong></summary>
          <div className="match-source-list">
            {match.sources.map((source) => <a href={source.url} key={source.id} rel="noreferrer" target="_blank"><span>{source.sourceName}</span><strong>{source.title ?? source.documentType}</strong>{source.author && <small>{source.author}</small>}</a>)}
          </div>
        </details>
      </section>
    </main>
  );
}
