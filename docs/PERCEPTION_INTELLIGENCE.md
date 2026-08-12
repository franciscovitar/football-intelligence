# Perception Intelligence V1

Block 9 creates an auditable qualitative evidence layer for player perception.
Its version is `perception-v1.0`.

It does **not** calculate a perception score, sentiment score, consensus,
Overrated, or Underrated. Those comparisons belong to Block 10.

## Source registry

Sources are explicit records with:

- stable code and display name;
- kind: `expert`, `media`, `fan`, or `other`;
- homepage and RSS/Atom feed URL;
- active/inactive state.

The checked-in V1 configuration starts with two `media` feeds:

- The Guardian · Football;
- ESPN · Soccer.

The data model already supports expert and fan sources, but V1 does not invent
unverified feeds merely to fill every source category.

## Feed and attribution boundary

V1 reads repository-controlled public HTTPS RSS/Atom feeds. It stores only the
fields exposed by the feed that are useful for evidence:

- title;
- feed excerpt/summary when present;
- canonical article URL;
- publication time;
- feed identifier;
- source provenance.

The web always names the source and links to the original article. It does not
scrape linked article pages.

Source-specific terms still apply. Before adding a new feed, confirm that its
publisher permits the intended use.

## Fetch safety

The feed client is intentionally narrow:

- HTTPS only;
- no URL userinfo;
- default HTTPS port only;
- DNS resolution must point to public/global addresses;
- redirects are manual, capped, and revalidated;
- requests have a bounded timeout;
- responses are capped at 2 MB;
- obvious HTML responses are rejected;
- RSS/Atom/XML is the accepted content family.

Feed URLs come from repository configuration, not from browser/user input.

## Normalization and deduplication

Article URLs are canonicalized by:

- lowercasing scheme/host;
- removing fragments;
- removing common tracking parameters such as `utm_*`, `fbclid`, and `gclid`;
- sorting remaining query parameters.

Idempotency is enforced by source + external feed ID when available and by
source + canonical URL.

Cross-source duplicates are retained for provenance but linked through
`duplicate_of_id`. The canonical evidence view excludes duplicate rows so that
the same syndicated claim cannot later inflate perception simply because it was
published in more than one feed.

Content equivalence in V1 uses SHA-256 over normalized title + excerpt. This is
a deterministic deduplication heuristic, not semantic similarity.

## Player linking

V1 entity linking is deliberately conservative and deterministic.

- active player display names are Unicode-normalized and case-folded;
- only a display name that maps uniquely to one player is eligible;
- the full normalized display name must appear on text boundaries in
  title + excerpt;
- ambiguous duplicate names are not linked;
- no LLM decides whether an article refers to a player;
- no aliases or nickname inference are invented in V1.

Persisted mention provenance records the player, matched display name, method,
and a short context excerpt.

## Persistence

PostgreSQL stores:

- `perception.sources`;
- `perception.evidence_items`;
- `perception.player_evidence_mentions`.

Generic ingestion execution metadata reuses `ingestion.ingestion_runs` through
the dedicated provider code `perception-web`.

Public database access to the perception schema/tables is revoked.

## Batch behavior

`football-intelligence-perception-ingest`:

1. validates and upserts the checked-in source registry;
2. records one ingestion run;
3. fetches each active source independently;
4. parses RSS/Atom;
5. canonicalizes and deduplicates evidence;
6. links unambiguous full player names;
7. persists evidence and mentions idempotently;
8. writes a JSON report.

One broken external source does not discard evidence fetched successfully from
other sources. A mixed run is persisted as `partial`. If every active source
fails, the job reports failure and exits non-zero.

The separate `Perception Evidence Sync` workflow keeps public-media outages from
breaking the core football data synchronization workflow.

## Web

`/perception` exposes:

- source coverage;
- source-kind filtering;
- evidence/player search;
- recent canonical evidence;
- publisher attribution and original links;
- linked players.

Player detail exposes recent canonical external evidence for that player.

The UI explicitly states that evidence is not a verdict or score.

## Testing boundary

CI is deterministic and does not depend on live public feeds.

It verifies:

- RSS and Atom parsing;
- URL canonicalization;
- content hashing;
- conservative player linking;
- database constraints;
- idempotent persistence;
- cross-source deduplication;
- mentions;
- `/perception` read path;
- player-detail evidence rendering.

Live publisher availability is an external runtime concern. Production
Supabase/Vercel configuration and a real scheduled feed run are separate
operational checkpoints.

## Block 10 boundary

Block 10 may consume this evidence only with explicit confidence gates and
deduplication semantics. It must not treat source count as independent consensus
when multiple rows represent the same underlying evidence.
