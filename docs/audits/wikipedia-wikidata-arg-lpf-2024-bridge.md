# Wikipedia → Wikidata identity bridge lab — ARG_LPF 2024

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: technical spike; no canonical players, database writes, crosswalks, or product promotion.

## Question

For the zero-cost historical active-squad evidence measured in `wikipedia-arg-lpf-2024-roster-lab.md`, how much player identity can be bridged deterministically from the player link stored in Wikipedia to a Wikidata item without fuzzy-name matching?

## Method

The lab repeats the accepted English-Wikipedia exact-revision active-squad extraction for the four 2024 snapshots and retains two provider-local fields from each inline player row:

- display name;
- linked English-Wikipedia article title when the historical row contains one.

It then calls the official English-Wikipedia MediaWiki Action API with `prop=pageprops` / `ppprop=wikibase_item`, honoring normalization and redirects, to resolve the linked article to its Wikidata QID.

No unlinked plain-text name is assigned a QID. Exact name alone is not used to bridge identity.

A QID remains provider-local identity evidence and does not become a Football Intelligence player ID.

## Real run

- commit: `ffe338f7057d680eaff8a08086f685fd3dd26688`;
- workflow run: `32915252610`;
- job: `98017514859`;
- artifact: `9587948792`;
- artifact digest: `sha256:0ed1a113b56578d2657c2bd49d14b616110bb33c565dc96be9a1340447a4c434`;
- technical result: SUCCESS.

## Result

Across the 26 clubs with accepted English historical active-squad sections:

- observed provider-local club-membership entries under the stricter identity-preserving union: **1,087**;
- entries with an explicit Wikipedia article link: **765 / 1,087 = 70.38%**;
- entries resolving through that link to a Wikidata QID: **748 / 1,087 = 68.81%**;
- QID resolution among explicitly linked entries: **748 / 765 = 97.78%**;
- unique linked Wikipedia article titles: **710**;
- unique Wikidata QIDs: **677**;
- QIDs reached from more than one historical article-title spelling/redirect: **8**.

The `1,087` count is slightly higher than the earlier display-name-only union (`1,075`) because this bridge deliberately does **not** collapse an unlinked plain-text row and a linked row merely because their display names look equal. That conservative behavior avoids manufacturing identity evidence.

Seventeen explicitly linked historical article titles currently resolve to missing pages/no Wikidata QID in this API path. Those remain unresolved. The much larger plain-text-only remainder also remains unresolved rather than receiving a guessed QID.

## Interpretation

This is a strong positive result for the free source stack:

- Wikipedia historical revisions can provide dated club-membership evidence for 26/28 clubs;
- when the historical squad row contains a biography link, the article → QID bridge succeeds **97.78%** of the time;
- roughly **68.8% of all conservatively retained membership entries** therefore already have deterministic Wikidata identity evidence without fuzzy matching.

This does **not** mean 68.8% of the official LPF roster is canonically resolved. The denominator is the Wikipedia historical membership-evidence set, whose semantics are active-squad listing, not AFA registration or Torneo appearance.

## Remaining limits

1. `Independiente Rivadavia` and `Vélez Sarsfield` remain absent from the accepted English-Wikipedia active-squad path.
2. The Spanish-Wikipedia Independiente Rivadavia 2024 plantel section cites Transfermarkt, so it is not accepted as a way to bypass the repository's Transfermarkt compliance decision.
3. The Spanish-Wikipedia Vélez 2024 section cites the official club roster page and remains a candidate for a separate correct extractor/primary historical snapshot.
4. About 29.6% of conservative membership entries have no explicit Wikipedia article link and therefore receive no QID from this bridge.
5. A Wikipedia→Wikidata QID is strong provider-local identity evidence but still does not satisfy the existing generic FI `crosswalk_ready` shared-match requirement by itself.
6. Profile completeness for these Argentina QIDs was not measured in this bridge run. The existing Wikidata parser and bounded 50-QID snapshot contract remain the next safe mechanism for that question.

## Decision

The Wikipedia → Wikidata bridge is **viable and worth retaining as the next zero-cost source path**, subject to a production-oriented provenance/licence review before promotion.

Recommended no-spend sequence:

```text
OpenFootball
  -> competition / club / fixture spine

Wikipedia exact 2024 historical revisions
  -> dated active-squad membership evidence
  -> explicit historical article target when present

MediaWiki pageprops.wikibase_item
  -> deterministic Wikipedia article -> Wikidata QID bridge

bounded Wikidata profile snapshots
  -> DOB / citizenship / position / height/profile evidence

LPF official final report
  -> independent club-level players-used validation totals
```

Unresolved entries and clubs stay unresolved. Missing evidence is never converted into zero or inferred membership.