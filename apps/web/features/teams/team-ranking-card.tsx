import Link from "next/link";

import { formatConfidence, formatScore } from "@/lib/player-display";
import type { RankingTeam } from "@/lib/queries/team-analytics";
import { RESULTS_PROCESS_LABELS } from "@/lib/team-display";

function optionalScore(value: number | undefined): string {
  return value === undefined ? "—" : formatScore(value);
}

export function TeamRankingCard({
  team,
  rank,
  competitionCode,
}: {
  team: RankingTeam;
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
              {team.matches} PJ · Elo {Math.round(team.currentElo)} · confianza {formatConfidence(team.confidence)}
            </p>
          </div>
          <div className="score-lockup">
            <strong>{formatScore(team.overallScore)}</strong>
            <span>Overall</span>
          </div>
        </div>
        <div className="ranking-footer">
          <span className="dimension-chip">
            Proceso {optionalScore(team.dimensionScores.process)} · Resultados {optionalScore(team.dimensionScores.results)}
          </span>
          {team.formScore === null ? null : (
            <span className="dimension-chip">Forma {formatScore(team.formScore)}</span>
          )}
          <span className="dimension-chip">{RESULTS_PROCESS_LABELS[team.resultsProcessSignal]}</span>
        </div>
      </div>
    </article>
  );
}
