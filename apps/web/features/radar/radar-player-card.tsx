import { formatConfidence, formatScore } from "@/lib/player-display";
import { RADAR_REASON_LABELS, formatMetric } from "@/lib/world-radar-display";
import type { WorldRadarPlayer } from "@/lib/queries/world-radar";

export function RadarPlayerCard({
  player,
  rank,
}: {
  player: WorldRadarPlayer;
  rank: number;
}) {
  return (
    <article className="ranking-card">
      <div className="ranking-position">{String(rank).padStart(2, "0")}</div>
      <div className="ranking-main">
        <div className="ranking-title-row">
          <div>
            <span className="player-link">{player.playerName}</span>
            <p className="ranking-meta">
              {player.teamName ?? "Equipo no informado"} · {player.competitionName} (
              {player.country})
              {player.position ? ` · ${player.position}` : ""}
            </p>
          </div>
          <div className="score-lockup">
            <strong>{formatScore(player.radarScore)}</strong>
            <span>
              Goles/90 {formatMetric(player.metrics.goals_per90)} · Asist/90{" "}
              {formatMetric(player.metrics.assists_per90)} · Pases clave/90{" "}
              {formatMetric(player.metrics.key_passes_per90)}
            </span>
          </div>
        </div>
        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Confianza {formatConfidence(player.confidence)}</span>
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(player.confidence * 100)}%` }} />
            </span>
          </div>
          <span className="dimension-chip">
            {player.sourceLists.join(" + ") || "sin feed"} ·{" "}
            {player.reasons.map((reason) => RADAR_REASON_LABELS[reason] ?? reason).join(", ") ||
              "sin señales adicionales"}
          </span>
        </div>
      </div>
    </article>
  );
}
