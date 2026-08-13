# Perception Inbox

An external Google Sheet, **"Football Intelligence — Perception Inbox"**,
now exists as the landing zone for a ChatGPT daily task that researches and
records qualitative football opinion/claims. This document is the contract
for that Sheet. Block 14 documents and validates the contract; it does
**not** implement the Sheet -> Supabase ingestion pipeline.

## Boundary (read this first)

This is qualitative evidence. It belongs to the Perception Intelligence lane
(see [`PERCEPTION_INTELLIGENCE.md`](PERCEPTION_INTELLIGENCE.md)) exclusively.

- It must **never** enter objective reconciliation
  (`data_mesh.reconciliation`) or the Coverage Lab.
- It must **never** modify an objective statistic or a quantitative
  performance value.
- `analytics/.../perception/inbox_schema.py`'s `InboxSourceType` vocabulary
  (`expert`/`media`/`fan`/`other`) shares **no values** with
  `data_mesh.models.SourceType`'s `objective_*` members -- a parsed inbox
  row cannot be type-confused with an objective observation.

## What Block 14 does and does not do

Does:

- documents the full Sheet contract below;
- adds `PerceptionInboxRow`, a pure, frozen DTO;
- adds `parse_inbox_row()`, a pure validation/parser function operating on a
  plain `dict[str, str]` (one already-fetched Sheet row) -- no Google API
  calls happen inside it.

Does not:

- read the Google Sheet (no Google API client, no service account, no
  credentials);
- store or reference the spreadsheet URL/ID anywhere in code;
- persist inbox rows to any database;
- let inbox rows influence objective stats, coverage, or reconciliation.

Actual Sheet -> Supabase ingestion and authentication (a scheduled fetch,
service-account setup, and persistence into `perception.*`) is explicitly
future work for a later block.

## Sheet structure

Tabs: **Inbox**, **Source Registry**, **Runs**. Only the **Inbox** tab's
schema is validated in this block.

### Inbox columns

| Column | Required | Notes |
| --- | --- | --- |
| `evidence_id` | yes | Sheet-assigned identifier |
| `collected_at` | yes | ISO-8601 timestamp; parsed as UTC |
| `published_at` | no | ISO-8601 timestamp of original publication |
| `competition_code` | no | Free text, not yet cross-checked against canonical competition codes |
| `entity_type` | yes | One of `player`, `team`, `competition`, `match` |
| `entity_name` | yes | As written by the research task, not yet linked to a canonical entity |
| `entity_hint` | no | Extra disambiguation text (team, position, etc.) |
| `source_type` | yes | One of `expert`, `media`, `fan`, `other` -- deliberately disjoint from any objective source type |
| `source_name` | yes | Publication/outlet/account name |
| `author` | no | Byline, if available |
| `source_url` | no | Original article/post URL |
| `claim_type` | yes | Free text category (e.g. `performance_opinion`, `transfer_rumor`) |
| `claim` | yes | The actual claim/quote text |
| `topic` | no | Free text topic tag |
| `sentiment` | no | Free text for now (not yet enum-constrained; see Known limitations) |
| `stance` | no | Free text for now |
| `credibility_score` | no | Numeric, must parse to a float in `[0, 1]` if present |
| `confidence` | no | Numeric, must parse to a float in `[0, 1]` if present |
| `consensus_key` | no | Free text grouping key for later consensus analysis |
| `language` | no | Free text language code |
| `country` | no | Free text country code |
| `processed` | no | Truthy string (`true`/`1`/`yes`/`y`) or blank/false |
| `processed_at` | no | ISO-8601 timestamp |
| `notes` | no | Free text |

Required columns (`REQUIRED_COLUMNS` in code): `evidence_id`,
`collected_at`, `entity_type`, `entity_name`, `source_type`, `source_name`,
`claim_type`, `claim`. A row missing any of these, or with an
`entity_type`/`source_type` outside the enums above, or a numeric field
outside `[0, 1]`, or an unparseable `collected_at`, raises `InboxRowError`
and is rejected -- never silently coerced.

## Known limitations

- `sentiment`/`stance` are accepted as free text in V0, not yet
  enum-validated, since the ChatGPT task's actual value vocabulary has not
  been observed/finalized yet. A future block should tighten this once real
  Sheet data exists.
- `competition_code`/`entity_name` are not yet cross-checked against
  canonical `football.*` identifiers -- that linking is deliberately
  conservative future work, following the same "UNRESOLVED is safer than
  wrong" principle as `data_mesh.entity_resolution`.
- No deduplication logic exists yet for inbox rows (Perception
  Intelligence's existing RSS pipeline has its own; the inbox will need an
  equivalent before real ingestion).

## Future ingestion lane (not built yet)

```text
ChatGPT/web research
    -> Google Sheet perception inbox (this document's contract)
    -> qualitative source adapter (reads the Sheet, calls parse_inbox_row)
    -> perception evidence (perception.* schema)
    -> Supabase
    -> Player/Team context
```

This lane converges only at the insight/product layer, never inside
objective statistics or reconciliation.
