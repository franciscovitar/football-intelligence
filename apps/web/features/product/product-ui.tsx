import Link from "next/link";
import type { ReactNode } from "react";

import {
  EVIDENCE_LABELS,
  formatNumber,
  formatScore,
  humanMetric,
  stateExplanation,
} from "@/lib/product-display";
import type {
  ProductDimensionEvidence,
  ProductMetric,
  ProductPlayerRanking,
  ProductTeamRanking,
} from "@/lib/queries/product-intelligence";
import type { ScoreEvidenceState } from "@/lib/queries/player-analytics";

export function EvidenceBadge({ state }: { state: ScoreEvidenceState }) {
  return <span className={`evidence-badge evidence-${state}`}>{EVIDENCE_LABELS[state]}</span>;
}

export function Confidence({ value, coverage }: { value: number; coverage?: number }) {
  return (
    <div className="confidence-block">
      <span>Confianza {Math.round(value * 100)}%</span>
      {coverage === undefined ? null : <span>Evidencia {Math.round(coverage)}%</span>}
      <div className="confidence-track" aria-hidden="true">
        <span style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}

export function ScoreBadge({ score, state }: { score: number | null; state: ScoreEvidenceState }) {
  return (
    <div className="product-score-badge">
      <strong>{formatScore(score)}</strong>
      <EvidenceBadge state={state} />
    </div>
  );
}

export function EmptyState({
  title,
  missing,
  unlock,
  compact = false,
}: {
  title: string;
  missing: string;
  unlock: string;
  compact?: boolean;
}) {
  return (
    <article className={`empty-product-state${compact ? " compact" : ""}`}>
      <span>No disponible todavía</span>
      <h3>{title}</h3>
      <p>{missing}</p>
      <small>{unlock}</small>
    </article>
  );
}

export function DimensionCard({
  label,
  evidence,
}: {
  label: string;
  evidence: ProductDimensionEvidence | undefined;
}) {
  const state = evidence?.evidenceState ?? "insufficient_data";
  return (
    <article className="dimension-card">
      <div className="dimension-card-head">
        <div>
          <span>{label}</span>
          <strong>{formatScore(evidence?.score ?? null)}</strong>
        </div>
        <EvidenceBadge state={state} />
      </div>
      <div className="coverage-track" aria-hidden="true">
        <span style={{ width: `${Math.round(evidence?.evidenceCoveragePct ?? 0)}%` }} />
      </div>
      <small>Cobertura {Math.round(evidence?.evidenceCoveragePct ?? 0)}%</small>
      <p>{stateExplanation(state, evidence?.missingMetrics)}</p>
      {evidence?.availableMetrics.length ? (
        <div className="evidence-chips">
          {evidence.availableMetrics.slice(0, 3).map((metric) => (
            <span key={metric}>{humanMetric(metric)}</span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function MetricRow({ metric }: { metric: ProductMetric }) {
  const primary = metric.adjustedValue ?? metric.per90Value ?? metric.rawValue;
  return (
    <div className="product-metric-row">
      <div>
        <strong>{humanMetric(metric.metricName)}</strong>
        <span>
          {metric.comparisonGroup ?? "Sin población comparable"} · muestra {metric.referenceSampleSize}
        </span>
      </div>
      <div className="metric-values">
        <strong>{formatNumber(primary, metric.metricUnit)}</strong>
        {metric.per90Value === null ? null : <span>{formatNumber(metric.per90Value)} /90</span>}
        {metric.percentile === null ? (
          <small>Percentil no disponible</small>
        ) : (
          <span className="metric-percentile">P{Math.round(metric.percentile)}</span>
        )}
      </div>
    </div>
  );
}

export function PlayerProductCard({
  player,
  rank,
  prominent = false,
}: {
  player: ProductPlayerRanking;
  rank: number;
  prominent?: boolean;
}) {
  return (
    <Link className={`product-ranking-card${prominent ? " prominent" : ""}`} href={`/player/${player.playerId}`}>
      <span className="rank-number">#{rank}</span>
      <div className="ranking-identity">
        <strong>{player.playerName}</strong>
        <span>{player.teamName ?? "Equipo no disponible"} · {player.positionFamily ?? player.role}</span>
        <small>{player.minutes} min · {Math.round(player.confidence * 100)}% confianza</small>
        <small>{player.keyEvidence.length ? player.keyEvidence.map(humanMetric).join(" · ") : `Evidencia ${Math.round(player.evidenceCoveragePct)}%`}</small>
      </div>
      <strong className="ranking-score">{formatScore(player.score)}</strong>
    </Link>
  );
}

export function TeamProductCard({ team, rank }: { team: ProductTeamRanking; rank: number }) {
  return (
    <Link className="product-ranking-card" href={`/team/${team.teamId}`}>
      <span className="rank-number">#{rank}</span>
      <div className="ranking-identity">
        <strong>{team.teamName}</strong>
        <span>{team.competitionName} · {team.seasonLabel}</span>
        <small>{team.matches} PJ · {Math.round(team.confidence * 100)}% confianza</small>
        <small>{team.keyEvidence.length ? team.keyEvidence.map(humanMetric).join(" · ") : `Evidencia ${Math.round(team.evidenceCoveragePct)}%`}</small>
      </div>
      <strong className="ranking-score">{formatScore(team.score)}</strong>
    </Link>
  );
}

export function Section({ eyebrow, title, action, children }: { eyebrow: string; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel product-section">
      <div className="section-heading">
        <div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function ComparisonRow({ label, left, right }: { label: string; left: number | null; right: number | null }) {
  const available = left !== null && right !== null;
  return (
    <div className="comparison-row">
      <strong className={available && left > right ? "comparison-winner" : ""}>{formatScore(left)}</strong>
      <div><span>{label}</span><small>{available ? (left === right ? "Evidencia pareja" : left > right ? "Ventaja izquierda" : "Ventaja derecha") : "Comparación inconclusa"}</small></div>
      <strong className={available && right > left ? "comparison-winner" : ""}>{formatScore(right)}</strong>
    </div>
  );
}
