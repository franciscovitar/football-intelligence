import Link from "next/link";

import { formatConfidence, formatScore, ROLE_LABELS_SINGULAR } from "@/lib/player-display";
import { formatSigned, SURPRISE_LABELS, TREND_LABELS, WATCHLIST_LABELS } from "@/lib/meta-display";
import type { MetaPlayer } from "@/lib/queries/meta-analytics";

export function MetaPlayerCard({
  player,
  rank,
  emphasis,
}: {
  player: MetaPlayer;
  rank: number;
  emphasis: "stable" | "surprise" | "trend" | "watchlist";
}) {
  const headline =
    emphasis === "stable"
      ? `Nivel ${formatScore(player.stableScore)}`
      : emphasis === "surprise"
        ? formatSigned(player.surpriseDelta)
        : emphasis === "trend"
          ? formatSigned(player.trendDelta)
          : `Watch ${formatScore(player.watchlistScore)}`;

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
              {ROLE_LABELS_SINGULAR[player.role]} · {SURPRISE_LABELS[player.surpriseSignal] ?? player.surpriseSignal}
            </p>
          </div>
          <div className="score-lockup">
            <strong>{headline}</strong>
            <span>{TREND_LABELS[player.trendSignal] ?? player.trendSignal}</span>
          </div>
        </div>
        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Confianza estable {formatConfidence(player.stableConfidence)}</span>
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(player.stableConfidence * 100)}%` }} />
            </span>
          </div>
          <span className="dimension-chip">
            {WATCHLIST_LABELS[player.watchlistSignal] ?? player.watchlistSignal}
          </span>
        </div>
      </div>
    </article>
  );
}
