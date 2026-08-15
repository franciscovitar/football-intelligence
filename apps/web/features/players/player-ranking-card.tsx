import Link from "next/link";

import {
  DIMENSION_LABELS,
  formatConfidence,
  formatScore,
  ROLE_LABELS_SINGULAR,
} from "@/lib/player-display";
import { POSITION_FAMILY_LABELS, type PositionFamily } from "@/lib/position-family";
import type { RankingPlayer } from "@/lib/queries/player-analytics";

export function PlayerRankingCard({
  player,
  rank,
  positionFamily,
}: {
  player: RankingPlayer;
  rank: number;
  positionFamily?: PositionFamily | null;
}) {
  // Top contributing dimensions double as the "top contributing percentiles"
  // signal for a ranking row: each dimension score is already a 0-100
  // role-relative aggregate, the same scale the player-detail page's
  // percentile evidence uses.
  const topDimensions = Object.entries(player.dimensionScores)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2);

  return (
    <article className="ranking-card">
      <div className="ranking-position" aria-label={`Puesto ${rank}`}>
        {String(rank).padStart(2, "0")}
      </div>
      <div className="ranking-main">
        <div className="ranking-title-row">
          <div>
            <Link className="player-link" href={`/player/${player.playerId}`}>
              {player.playerName}
            </Link>
            <p className="ranking-meta">
              {ROLE_LABELS_SINGULAR[player.role]}
              {positionFamily ? ` · ${POSITION_FAMILY_LABELS[positionFamily]}` : ""} ·{" "}
              {player.minutes} min · {player.appearances} PJ
            </p>
          </div>
          <div className="score-lockup">
            <strong>{formatScore(player.overallScore)}</strong>
            <span>score</span>
          </div>
        </div>

        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Confianza {formatConfidence(player.confidence)}</span>
            <span>Evidencia {Math.round(player.evidenceCoveragePct)}%</span>
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(player.confidence * 100)}%` }} />
            </span>
          </div>
          {topDimensions.map(([dimension, value]) => (
            <span className="dimension-chip" key={dimension}>
              {DIMENSION_LABELS[dimension] ?? dimension} {formatScore(value)}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}
