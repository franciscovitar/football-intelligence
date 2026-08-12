import Link from "next/link";

import { formatConfidence, formatScore } from "@/lib/player-display";
import type { TacticalTeam } from "@/lib/queries/tactical-intelligence";
import {
  FORMATION_SIGNAL_LABELS,
  TACTICAL_DEFENSE_LABELS,
  TACTICAL_STYLE_LABELS,
} from "@/lib/tactical-display";

export function TacticalTeamCard({
  team,
  rank,
  competitionCode,
}: {
  team: TacticalTeam;
  rank: number;
  competitionCode: string;
}) {
  return (
    <article className="ranking-card">
      <div className="ranking-position">{String(rank).padStart(2, "0")}</div>
      <div className="ranking-main">
        <div className="ranking-title-row">
          <div>
            <Link
              className="player-link"
              href={`/team/${team.teamId}?competition=${encodeURIComponent(competitionCode)}`}
            >
              {team.teamName}
            </Link>
            <p className="ranking-meta">
              {TACTICAL_STYLE_LABELS[team.styleSignal] ?? team.styleSignal} ·{" "}
              {TACTICAL_DEFENSE_LABELS[team.defensiveSignal] ?? team.defensiveSignal}
            </p>
          </div>
          <div className="score-lockup">
            <strong>{team.primaryFormation ?? "—"}</strong>
            <span>
              {FORMATION_SIGNAL_LABELS[team.formationSignal] ?? team.formationSignal}
            </span>
          </div>
        </div>
        <p className="ranking-summary">{team.summary}</p>
        <div className="ranking-footer">
          <div className="confidence-line">
            <span>Confianza {formatConfidence(team.tacticalConfidence)}</span>
            <span className="confidence-track" aria-hidden="true">
              <span style={{ width: `${Math.round(team.tacticalConfidence * 100)}%` }} />
            </span>
          </div>
          <span className="dimension-chip">
            Control {team.controlScore === null ? "—" : formatScore(team.controlScore)} ·
            Volumen{" "}
            {team.attackingVolumeScore === null
              ? "—"
              : formatScore(team.attackingVolumeScore)}
          </span>
        </div>
      </div>
    </article>
  );
}
