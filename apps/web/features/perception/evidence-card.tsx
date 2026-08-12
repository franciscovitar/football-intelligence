import Link from "next/link";

import { formatDateTime } from "@/lib/player-display";
import type { PerceptionEvidence } from "@/lib/queries/perception";

const KIND_LABELS = {
  expert: "Experto",
  media: "Medio",
  fan: "Fans",
  other: "Otro",
} as const;

export function PerceptionEvidenceCard({
  evidence,
}: {
  evidence: PerceptionEvidence;
}) {
  return (
    <article className="ranking-card">
      <div className="ranking-position" aria-hidden="true">
        EXT
      </div>
      <div className="ranking-main">
        <div className="ranking-title-row">
          <div>
            <a
              className="player-link"
              href={evidence.canonicalUrl}
              rel="noreferrer"
              target="_blank"
            >
              {evidence.title} ↗
            </a>
            <p className="ranking-meta">
              {evidence.sourceName} · {KIND_LABELS[evidence.sourceKind]} ·{" "}
              {formatDateTime(evidence.publishedAt ?? evidence.discoveredAt)}
            </p>
          </div>
        </div>

        {evidence.excerpt ? <p className="team-copy">{evidence.excerpt}</p> : null}

        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Provenance: {evidence.sourceCode}</span>
          </div>
          {evidence.linkedPlayers.map((player) => (
            <Link
              className="dimension-chip"
              href={`/player/${player.playerId}`}
              key={player.playerId}
            >
              {player.playerName}
            </Link>
          ))}
        </div>
      </div>
    </article>
  );
}
