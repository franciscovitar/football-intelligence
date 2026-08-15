\set ON_ERROR_STOP on

begin;

-- `diagnostic_findings` previously had no way to prove a row's provenance:
-- a legacy/smoke row for entity_id X could leak into the product merely
-- because X also happens to have a real V2 score elsewhere (the read path
-- only checked entity existence, never the finding's own context). These
-- three columns make provenance explicit instead of inferred.
--
-- `data_context` defaults to 'test_smoke' -- the inverse of every other
-- product `data_context` default in this schema (see
-- `player_score_snapshots`, `player_feature_snapshots`, etc., which default
-- to 'real'). That inversion is intentional: unlike those tables, this one
-- has no real writer yet -- every row that predates this migration came
-- from the deterministic smoke fixture, so the conservative and correct
-- backfill is "not product-safe" rather than "real". A future real writer
-- must explicitly set data_context = 'real'.
alter table analytics.diagnostic_findings
    add column data_context text not null default 'test_smoke',
    add column source_model_version text not null default 'unknown',
    add column scope_key text not null default 'unknown';

alter table analytics.diagnostic_findings
    add constraint diagnostic_findings_data_context_check
        check (data_context in ('real', 'test_smoke')),
    add constraint diagnostic_findings_source_model_version_not_blank_check
        check (btrim(source_model_version) <> ''),
    add constraint diagnostic_findings_scope_key_not_blank_check
        check (btrim(scope_key) <> '');

create index diagnostic_findings_product_context_idx
    on analytics.diagnostic_findings (
        entity_type,
        data_context,
        source_model_version,
        scope_key,
        diagnostic_code
    );

-- "Active scope" mirrors exactly how the application already picks the
-- live scope for Home/Rankings/Player: the (scope_key, model_version) pair
-- with the freshest real V2 snapshot. A diagnostic finding tied to a scope
-- that is no longer the active one must not resurface once a newer scope
-- has taken over, so the product-safe views below inner-join against it
-- instead of trusting whatever scope_key a row happens to carry.
create view analytics.product_active_player_scope_v2 as
select scope_key, model_version, max(calculated_at) as calculated_at
from analytics.product_player_detail_v2
group by scope_key, model_version
order by max(calculated_at) desc
limit 1;

create view analytics.product_active_team_scope_v2 as
select scope_key, model_version, max(calculated_at) as calculated_at
from analytics.product_team_detail_v2
group by scope_key, model_version
order by max(calculated_at) desc
limit 1;

-- Product-safe diagnostic findings: real data_context, sourced from the
-- corresponding V2 statistical model (not merely the diagnostic-rule
-- engine version, which is a separate concept -- see `model_version` on
-- this table), and scoped to whichever snapshot is currently active.
create view analytics.product_player_diagnostic_findings_v2 as
select finding.*
from analytics.diagnostic_findings as finding
join analytics.product_active_player_scope_v2 as active
    on finding.scope_key = active.scope_key
where finding.entity_type = 'player'
  and finding.data_context = 'real'
  and finding.source_model_version = 'player-v2.0';

create view analytics.product_team_diagnostic_findings_v2 as
select finding.*
from analytics.diagnostic_findings as finding
join analytics.product_active_team_scope_v2 as active
    on finding.scope_key = active.scope_key
where finding.entity_type = 'team'
  and finding.data_context = 'real'
  and finding.source_model_version = 'team-v2.0';

revoke all on analytics.product_active_player_scope_v2 from public;
revoke all on analytics.product_active_team_scope_v2 from public;
revoke all on analytics.product_player_diagnostic_findings_v2 from public;
revoke all on analytics.product_team_diagnostic_findings_v2 from public;

commit;
