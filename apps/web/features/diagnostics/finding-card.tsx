import Link from "next/link";

import {
  DIAGNOSTIC_SEVERITY_LABELS,
  DIAGNOSTIC_WINDOW_LABELS,
  diagnosticCodeToSentence,
} from "@/lib/diagnostics-display";
import { formatConfidence } from "@/lib/player-display";
import type { DiagnosticFinding } from "@/lib/queries/diagnostics";

const SEVERITY_CLASS: Record<DiagnosticFinding["severity"], string> = {
  info: "severity-badge severity-badge--info",
  notable: "severity-badge severity-badge--notable",
  high: "severity-badge severity-badge--high",
};

export function DiagnosticFindingCard({
  finding,
  entityName,
  entityHref,
}: {
  finding: DiagnosticFinding;
  entityName?: string;
  entityHref?: string;
}) {
  return (
    <article className="ranking-card diagnostic-card">
      <div className="diagnostic-card-head">
        <span className={SEVERITY_CLASS[finding.severity]}>
          {DIAGNOSTIC_SEVERITY_LABELS[finding.severity]}
        </span>
        {entityName && entityHref ? (
          <Link className="player-link" href={entityHref}>
            {entityName}
          </Link>
        ) : null}
      </div>
      <p className="team-copy">{diagnosticCodeToSentence(finding.diagnosticCode, finding.supportingMetrics)}</p>
      <div className="ranking-footer">
        <div className="confidence-line">
          <span>Confianza {formatConfidence(finding.confidence)}</span>
          <span className="confidence-track" aria-hidden="true">
            <span style={{ width: `${Math.round(finding.confidence * 100)}%` }} />
          </span>
        </div>
        <span className="dimension-chip">
          {DIAGNOSTIC_WINDOW_LABELS[finding.windowKey] ?? finding.windowKey} · {finding.comparisonGroup}
        </span>
      </div>
    </article>
  );
}
