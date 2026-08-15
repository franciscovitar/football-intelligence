"""Shared deterministic severity bucketing for diagnostic rules."""

from __future__ import annotations

from football_intelligence.diagnostics.models import DiagnosticSeverity


def severity_from_magnitude(
    magnitude: float,
    *,
    notable: float,
    high: float,
) -> DiagnosticSeverity:
    """Bucket an absolute signal magnitude into info/notable/high.

    Deterministic, no ML: `magnitude` is expected to already be a
    non-negative distance from whatever threshold the calling rule used to
    decide a finding fires at all (e.g. a percentile gap). Rules that only
    fire once a threshold is crossed will therefore never report "info" --
    that tier exists for rules that classify every value into a severity
    rather than gating on one.
    """

    absolute_magnitude = abs(magnitude)
    if absolute_magnitude >= high:
        return "high"
    if absolute_magnitude >= notable:
        return "notable"
    return "info"
