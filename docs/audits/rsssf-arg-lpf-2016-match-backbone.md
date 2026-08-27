# RSSSF ARG_LPF 2016 match-backbone audit

Status: **GO for a bounded historical fixture/result backbone; NO-GO for player participation/minutes**.

## Decision question

Can the RSSSF `Argentina 2016` document provide a zero-cost, reusable and sufficiently precise match backbone for the short Argentine Primera División 2016 tournament, so later player evidence can be scoped and reconciled against the correct matches/phases without inventing kickoff times or player participation?

## Source and reuse boundary

Reviewed source:

`https://www.rsssf.org/tablesa/arg2016.html`

The document identifies Osvaldo José Gorgazzi as author/maintainer and includes a document-specific notice permitting the document to be copied in whole or part when the author is properly acknowledged.

Football Intelligence treats this as a **bounded permission for this reviewed historical document**, not as a blanket open-data licence for all RSSSF content.

Required retained provenance for this integration includes at least:

- provider: `rsssf`;
- exact source URL;
- author attribution;
- acquisition timestamp;
- HTTP content type / decoded charset;
- raw-document SHA-256;
- parser semantic version;
- provider-local match identity;
- competition/season scope.

No raw HTML page or full 242-match extracted payload is committed to the canonical repository by this audit.

## Real-source spike

Successful bounded probe:

- workflow run: `33084890010`;
- artifact: `rsssf-arg-2016-match-backbone-v2-33084890010`;
- artifact id: `9651688991`;
- artifact digest: `sha256:dc3e9543a53fda9ed039a2ab2e2fbc24bdec0a5307986716240d49c3c9440ff1`;
- observed HTTP content type: `text/html; charset=windows-1252`;
- decoded charset: `windows-1252`;
- raw HTML digest at that acquisition: `sha256:de9bea28bd098cd7094581cf4595db9d95496d42763db8530154e3ee8b0eb566`.

The first probe had failed before parsing because it assumed an incompatible text decoding and therefore could not find the accented competition heading. The corrected probe used the server-declared charset plus normalized textual boundaries. This was an extraction defect, not a source-data failure.

## Tournament completeness result

The corrected real-source probe recovered exactly:

| Classification | Matches |
| --- | ---: |
| regular Group 1 | `105` |
| regular Group 2 | `105` |
| regular Intergroup | `30` |
| second-place / third-position playoff | `1` |
| championship final | `1` |
| **total** | **`242`** |

Additional hard checks passed:

- `240` regular matches;
- `15` matches in every round `1` through `16`;
- `2` matches in round `17`;
- `30` provider-local club labels;
- every one of the 30 club labels appears in exactly `16` regular matches;
- `242 / 242` matches have an explicit calendar date;
- `242 / 242` matches have a venue string;
- `242 / 242` provider-local match ids are unique;
- the second-place playoff is explicitly dated `2016-05-28`;
- the championship final is explicitly dated `2016-05-29`.

The production parser keeps those counts as fail-closed structural gates. A future page edit that no longer represents this certified tournament shape must raise a schema error instead of silently returning a partial backbone.

## Temporal precision

RSSSF publishes a **calendar date**, not a trustworthy kickoff clock time for these fixture rows.

Football Intelligence therefore:

- preserves `kickoff_date=YYYY-MM-DD` as match-identity context;
- does **not** emit `kickoff_at` from RSSSF;
- does **not** manufacture midnight or a timezone merely to satisfy a datetime-shaped DTO.

This reuses the existing OpenFootball/Data Mesh identity pattern: team identities + season + date are sufficient for conservative match resolution without fabricating precision the source does not provide.

## Provider-local match identity

RSSSF does not publish a stable machine match id in this document. The bounded adapter therefore derives a deterministic provider-local key from:

- match date;
- round number;
- explicit phase;
- home-team raw label;
- away-team raw label.

The score is deliberately excluded from the identity key. If the historical result is corrected upstream, that correction changes the score observation but must not manufacture a different logical match.

This provider-local id is not a Football Intelligence canonical match id.

## Adapter scope

The certified adapter is intentionally small.

For every parsed match it may emit:

- team identity/name evidence for home and away provider-local labels;
- `status = finished`;
- `round_name`;
- `venue_name`;
- `home_score`;
- `away_score`;
- match identity hints containing provider match id, competition id, season, home/away names and `kickoff_date`.

It must not emit from this fixture list:

- `kickoff_at`;
- player identities;
- player appearances;
- starts;
- minutes;
- lineups;
- player match statistics.

The separate RSSSF player-evidence audit found only one complete lineup block in the 242-match championship (the final), so that sparse detail cannot be generalized to the regular tournament.

## Entity-resolution boundary

The integration adds one explicit competition mapping only:

`rsssf:arg2016.html -> ARG_LPF`

This mapping is deliberately document-specific. It does not make `ARG_LPF`, another RSSSF year, or arbitrary RSSSF pages resolve automatically.

Raw RSSSF club labels remain provider-local evidence. The existing deterministic team-name resolution path may produce logical Data Mesh keys, but this audit creates no production `football.teams` rows and no player crosswalks.

## Decision

### Historical ARG_LPF 2016 fixture/result backbone

**GO.**

RSSSF is sufficiently complete and reusable for the narrow role of historical match structure/result corroboration for the short 2016 Primera División championship.

### Player participation/minutes backbone

**NO-GO.**

The source does not provide match-by-match lineups/minutes across the competition. Missing player evidence remains missing and cannot be inferred from fixture membership.

## Non-claims

- `242` certified fixture rows do not imply 242 lineup records.
- A club appearing in a fixture does not prove any specific player appeared.
- A calendar date is not a kickoff timestamp.
- `status=finished` is justified by the historical completed result row; it is not a live-status feed.
- RSSSF team strings are source-local labels, not canonical Football Intelligence identities.
- The document-specific copy notice is not generalized into a repository-wide RSSSF licence claim.
- No database ingestion or product promotion is performed by this audit itself.

## Implementation verification

The provider/adapter implementation must be considered complete only after:

1. focused provider, adapter, source-policy and Data Mesh resolution tests pass;
2. a live runtime fetch of the real RSSSF page produces the certified 242-match structure and the expected bounded observation set;
3. repository Quality passes;
4. disposable spike/runtime workflows are removed;
5. final Quality passes again after cleanup.

Run ids and final implementation counts are appended/recorded only after those checks have actually executed.
