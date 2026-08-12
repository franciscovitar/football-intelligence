import Link from "next/link";

import {
  DIMENSION_LABELS,
  formatConfidence,
  formatScore,
  ROLE_LABELS_SINGULAR,
} from "@/lib/player-display";
import type { RankingPlayer } from "@/lib/queries/player-analytics";

export function PlayerRankingCard({
  player,
  rank,
}: {
  player: RankingPlayer;
  rank: number;
}) {
  const primaryDimension = Object.entries(player.dimensionScores).sort((a, b) => b[1] - a[1])[0];

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
              {ROLE_LABELS_SINGULAR[player.role]} · {player.minutes} min · {player.appearances} PJ
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
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(player.confidence * 100)}%` }} />
            </span>
          </div>
          {primaryDimension ? (
            <span className="dimension-chip">
              {DIMENSION_LABELS[primaryDimension[0]] ?? primaryDimension[0]}{" "}
              {formatScore(primaryDimension[1])}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}
