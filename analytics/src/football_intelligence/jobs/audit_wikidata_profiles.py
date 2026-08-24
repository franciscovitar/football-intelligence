"""Audit a frozen Wikidata player-profile static snapshot.

Read-only. This job verifies the generic snapshot manifest/checksums first and
then reports how much identity/profile evidence the frozen Wikidata entities
actually contain. It does not create player crosswalks or write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from football_intelligence.ingestion.static_snapshot import (
    StaticSnapshotManifestError,
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)
from football_intelligence.providers.wikidata_profiles import (
    SOURCE_CODE,
    WikidataPlayerProfile,
    WikidataProfileError,
    load_wikidata_profile,
)


class WikidataProfileAuditError(RuntimeError):
    """A frozen Wikidata profile snapshot cannot be audited safely."""


@dataclass(frozen=True, slots=True)
class WikidataProfileAuditReport:
    snapshot_id: str
    profile_count: int
    profiles_with_label: int
    profiles_with_exact_date_of_birth: int
    profiles_with_partial_date_of_birth: int
    profiles_with_ambiguous_or_conflicting_date_of_birth: int
    profiles_with_citizenship: int
    profiles_with_position: int
    profiles_with_team_membership: int
    team_membership_count: int
    temporally_bounded_team_membership_count: int
    profiles_with_revision_id: int

    @property
    def passed(self) -> bool:
        return self.profile_count > 0 and self.profiles_with_label == self.profile_count


def audit_profiles(
    *, snapshot_id: str, profiles: tuple[WikidataPlayerProfile, ...]
) -> WikidataProfileAuditReport:
    exact_dob = 0
    partial_dob = 0
    ambiguous_dob = 0
    membership_count = 0
    bounded_memberships = 0

    for profile in profiles:
        exact = profile.exact_date_of_birth
        if exact is not None:
            exact_dob += 1
        elif profile.dates_of_birth:
            if any(value.date_bounds is not None for value in profile.dates_of_birth):
                partial_dob += 1
            if len(profile.dates_of_birth) > 1:
                ambiguous_dob += 1

        membership_count += len(profile.team_memberships)
        bounded_memberships += sum(
            1
            for membership in profile.team_memberships
            if len(membership.start_times) == 1
            and membership.start_times[0].date_bounds is not None
            and len(membership.end_times) == 1
            and membership.end_times[0].date_bounds is not None
        )

    return WikidataProfileAuditReport(
        snapshot_id=snapshot_id,
        profile_count=len(profiles),
        profiles_with_label=sum(profile.display_name is not None for profile in profiles),
        profiles_with_exact_date_of_birth=exact_dob,
        profiles_with_partial_date_of_birth=partial_dob,
        profiles_with_ambiguous_or_conflicting_date_of_birth=ambiguous_dob,
        profiles_with_citizenship=sum(bool(profile.citizenship_qids) for profile in profiles),
        profiles_with_position=sum(bool(profile.position_qids) for profile in profiles),
        profiles_with_team_membership=sum(bool(profile.team_memberships) for profile in profiles),
        team_membership_count=membership_count,
        temporally_bounded_team_membership_count=bounded_memberships,
        profiles_with_revision_id=sum(profile.last_revision_id is not None for profile in profiles),
    )


def run_audit(*, manifest_path: Path, base_dir: Path) -> WikidataProfileAuditReport:
    try:
        manifest = load_static_snapshot_manifest(manifest_path)
    except (OSError, json.JSONDecodeError, StaticSnapshotManifestError) as exc:
        raise WikidataProfileAuditError(f"invalid snapshot manifest: {exc}") from exc

    if manifest.source_code != SOURCE_CODE:
        raise WikidataProfileAuditError(
            f"expected source_code={SOURCE_CODE!r}, got {manifest.source_code!r}"
        )
    if "player_profile" not in manifest.data_grains:
        raise WikidataProfileAuditError("Wikidata snapshot must declare player_profile grain")

    verification = verify_static_snapshot_files(manifest, base_dir=base_dir)
    if not verification.passed:
        failed = [file.path for file in verification.files if not file.passed]
        raise WikidataProfileAuditError(f"snapshot integrity failed for files {failed!r}")

    profiles: list[WikidataPlayerProfile] = []
    for snapshot_file in manifest.files:
        path = base_dir / snapshot_file.path
        expected_qid = path.stem
        try:
            profiles.append(load_wikidata_profile(path, expected_qid=expected_qid))
        except (OSError, json.JSONDecodeError, WikidataProfileError) as exc:
            raise WikidataProfileAuditError(f"{snapshot_file.path}: {exc}") from exc

    return audit_profiles(snapshot_id=manifest.snapshot_id, profiles=tuple(profiles))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a frozen Wikidata profile snapshot.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(manifest_path=args.manifest, base_dir=args.base_dir)
    except WikidataProfileAuditError as exc:
        raise SystemExit(f"WIKIDATA PROFILE AUDIT: FAIL - {exc}") from exc

    payload = {"status": "PASS" if report.passed else "FAIL", **asdict(report)}
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    state = "PASS" if report.passed else "FAIL"
    print(
        f"WIKIDATA PROFILE AUDIT: {state} profiles={report.profile_count} "
        f"exact_dob={report.profiles_with_exact_date_of_birth} "
        f"team_memberships={report.team_membership_count} "
        f"bounded_memberships={report.temporally_bounded_team_membership_count}"
    )
    if not report.passed:
        raise SystemExit("WIKIDATA PROFILE AUDIT: FAIL")
    if args.report is not None:
        print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
