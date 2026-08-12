import Link from "next/link";

import { formatSigned } from "@/lib/meta-display";
import {
  formatConfidence,
  formatScore,
  ROLE_LABELS_SINGULAR,
} from "@/lib/player-display";
import {
  PERCEPTION_SIGNAL_LABELS,
  RATING_SIGNAL_LABELS,
} from "@/lib/rating-display";
import type { RatingPlayer } from "@/lib/queries/rating-intelligence";

export function RatingPlayerCard({
  player,
  rank,
  emphasis,
}: {
  player: RatingPlayer;
  rank: number;
  emphasis: "rating" | "consensus" | "polarization";
}) {
  const headline =
    emphasis === "consensus"
      ? `Consenso ${formatScore(player.consensusScore ?? 0)}`
      : emphasis === "polarization"
        ? `Polarización ${formatScore(player.polarizationScore ?? 0)}`
        : formatSigned(player.ratingGap);

  return (
    <article className="ranking-card">
      <div className="ranking-position">{String(rank).padStart(2, "0")}</div>
      <div className="ranking-main">
        <div className="ranking-title-row">
          <div>
            <Link className="player-link" href={`/player/${player.playerId}`}>
              {player.playerName}
            </Link>
            <p className="ranking-meta">
              {ROLE_LABELS_SINGULAR[player.role]} ·{" "}
              {RATING_SIGNAL_LABELS[player.ratingSignal] ?? player.ratingSignal}
            </p>
          </div>
          <div className="score-lockup">
            <strong>{headline}</strong>
            <span>
              Stable {formatScore(player.performanceScore)} · Percepción{" "}
              {player.perceptionScore === null ? "—" : formatScore(player.perceptionScore)}
            </span>
          </div>
        </div>
        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Confianza {formatConfidence(player.ratingConfidence)}</span>
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(player.ratingConfidence * 100)}%` }} />
            </span>
          </div>
          <span className="dimension-chip">
            {PERCEPTION_SIGNAL_LABELS[player.perceptionSignal] ?? player.perceptionSignal} ·{" "}
            {player.scoredEvidenceCount} evid. · {player.scoredSourceCount} fuentes
          </span>
        </div>
      </div>
    </article>
  );
}
