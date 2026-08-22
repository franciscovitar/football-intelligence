import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import postgres from "postgres";

const EXPECTED = {
  currentMatches: 380,
  currentTeamMatchStats: 760,
  historicalMatches: 380,
  historicalAppearances: 10443,
  historicalSourceObservations: 412609,
  playerV2Scores: 2048,
  playerV2Features: 26841,
};

if (!process.env.VERCEL || process.env.VERCEL_ENV !== "production") {
  console.log(`HISTORICAL PRODUCTION OPERATOR: SKIP ${process.env.VERCEL_ENV ?? "non-vercel"}`);
  process.exit(0);
}

const originalDatabaseUrl = process.env.DATABASE_URL;
if (!originalDatabaseUrl) {
  throw new Error("HISTORICAL PRODUCTION OPERATOR: DATABASE_URL is missing");
}

const parsed = new URL(originalDatabaseUrl);
if (!parsed.port) parsed.port = "5432";
const databaseUrl = parsed.toString();
const databaseName = parsed.pathname.replace(/^\//, "") || "(default)";
const safeTarget = `postgresql://${parsed.hostname}:${parsed.port}/${databaseName}`;
console.log(`HISTORICAL PRODUCTION OPERATOR TARGET: ${safeTarget}`);

const sql = postgres(databaseUrl, { max: 1, prepare: false });

async function readProductionState() {
  return sql.begin(async (tx) => {
    await tx.unsafe("SET TRANSACTION READ ONLY");

    const [views] = await tx`
      select
        to_regclass('analytics.product_team_detail_v2')::text as team_detail_v2,
        to_regclass('analytics.product_player_detail_v2')::text as player_detail_v2
    `;

    const [current] = await tx`
      with target_season as (
        select s.id
        from football.seasons s
        join football.competitions c on c.id = s.competition_id
        where c.code = 'ENG_PL' and s.label = '2025/26'
      )
      select
        (select count(*)::int from target_season) as season_rows,
        (select count(*)::int from football.matches m where m.season_id in (select id from target_season)) as matches,
        (select count(*)::int from football.team_match_stats tms join football.matches m on m.id=tms.match_id where m.season_id in (select id from target_season)) as team_match_stats
    `;

    const [historical] = await tx`
      with target_season as (
        select s.id
        from football.seasons s
        join football.competitions c on c.id = s.competition_id
        where c.code = 'ENG_PL' and s.label = '2017/18'
      )
      select
        (select count(*)::int from target_season) as season_rows,
        (select count(*)::int from football.matches m where m.season_id in (select id from target_season)) as matches,
        (select count(*)::int from football.player_appearances pa join football.matches m on m.id=pa.match_id where m.season_id in (select id from target_season)) as appearances,
        (select count(*)::int from analytics.player_score_snapshots ps where ps.scope_key='competition:ENG_PL:2017/18' and ps.model_version='player-v2.0') as player_v2_scores,
        (select count(*)::int from analytics.player_feature_snapshots pf where pf.scope_key='competition:ENG_PL:2017/18' and pf.model_version='player-v2.0') as player_v2_features,
        (select count(*)::int from ingestion.source_observations o join ingestion.providers p on p.id=o.provider_id where p.code='wyscout-open' and o.entity_identity_hints->>'season_label'='2017/18') as source_observations
    `;

    const [safety] = await tx`
      select
        (select count(*)::int from ingestion.providers where code='wyscout-open') as wyscout_provider_rows,
        (select count(*)::int from ingestion.source_observations where source_reference ilike '%test_smoke%') as test_smoke_rows
    `;

    return { views, current, historical, safety };
  });
}

async function readDataMeshSchemaState() {
  const [state] = await sql`
    select
      exists (
        select 1 from information_schema.columns
        where table_schema='ingestion' and table_name='source_observations'
          and column_name='metric_granularity'
      ) as source_metric_granularity,
      exists (
        select 1 from information_schema.columns
        where table_schema='ingestion' and table_name='reconciliation_decisions'
          and column_name='metric_granularity'
      ) as decision_metric_granularity,
      (select count(*)::int from ingestion.source_observations) as source_rows,
      (select count(*)::int from ingestion.reconciliation_decisions) as decision_rows,
      (
        select pg_get_constraintdef(c.oid)
        from pg_constraint c
        join pg_class r on r.oid=c.conrelid
        join pg_namespace n on n.oid=r.relnamespace
        where n.nspname='ingestion' and r.relname='source_observations'
          and c.conname='source_observations_natural_key'
      ) as source_natural_key,
      (
        select pg_get_constraintdef(c.oid)
        from pg_constraint c
        join pg_class r on r.oid=c.conrelid
        join pg_namespace n on n.oid=r.relnamespace
        where n.nspname='ingestion' and r.relname='reconciliation_decisions'
          and c.conname='reconciliation_decisions_natural_key'
      ) as decision_natural_key,
      (
        select pg_get_constraintdef(c.oid)
        from pg_constraint c
        join pg_class r on r.oid=c.conrelid
        join pg_namespace n on n.oid=r.relnamespace
        where n.nspname='ingestion' and r.relname='reconciliation_decisions'
          and c.conname='reconciliation_decisions_status_check'
      ) as decision_status_check
  `;
  return state;
}

async function ensureDataMeshV2Schema() {
  const before = await readDataMeshSchemaState();
  const sourceHasColumn = before.source_metric_granularity === true;
  const decisionHasColumn = before.decision_metric_granularity === true;

  requireCondition(
    sourceHasColumn === decisionHasColumn,
    `partial Data Mesh V2 schema detected: ${JSON.stringify(before)}`,
  );

  if (sourceHasColumn && decisionHasColumn) {
    requireCondition(
      before.source_natural_key?.includes("metric_granularity") &&
        before.source_natural_key?.includes("NULLS NOT DISTINCT"),
      "source_observations V2 natural key is not canonical",
    );
    requireCondition(
      before.decision_natural_key?.includes("metric_granularity") &&
        before.decision_natural_key?.includes("NULLS NOT DISTINCT"),
      "reconciliation_decisions V2 natural key is not canonical",
    );
    requireCondition(
      before.decision_status_check?.includes("methodology_pending") &&
        before.decision_status_check?.includes("not_comparable"),
      "reconciliation_decisions V2 status vocabulary is not canonical",
    );
    console.log("DATA MESH V2 SCHEMA: PASS already current");
    return;
  }

  requireCondition(before.source_rows === 0, "pre-V2 source_observations is not empty");
  requireCondition(before.decision_rows === 0, "pre-V2 reconciliation_decisions is not empty");
  requireCondition(
    before.source_natural_key && !before.source_natural_key.includes("metric_granularity"),
    "pre-V2 source_observations natural key is unexpected",
  );
  requireCondition(
    before.decision_natural_key && !before.decision_natural_key.includes("metric_granularity"),
    "pre-V2 reconciliation_decisions natural key is unexpected",
  );
  requireCondition(
    before.decision_status_check &&
      !before.decision_status_check.includes("methodology_pending") &&
      !before.decision_status_check.includes("not_comparable"),
    "pre-V2 reconciliation_decisions status vocabulary is unexpected",
  );

  await sql.begin(async (tx) => {
    await tx.unsafe(`
      alter table ingestion.source_observations
        add column metric_granularity text
    `);
    await tx.unsafe(`
      alter table ingestion.source_observations
        add constraint source_observations_metric_granularity_check
        check (
          metric_granularity is null
          or metric_granularity in (
            'competition', 'team', 'match', 'team_match', 'player_appearance',
            'player_match', 'player_season', 'goalkeeper_match', 'goalkeeper_season'
          )
        )
    `);
    await tx.unsafe(`
      alter table ingestion.source_observations
        drop constraint source_observations_natural_key
    `);
    await tx.unsafe(`
      alter table ingestion.source_observations
        add constraint source_observations_natural_key
        unique nulls not distinct (
          provider_id, entity_type, entity_source_id, metric_name,
          metric_granularity, observed_at
        )
    `);

    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        add column metric_granularity text
    `);
    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        add constraint reconciliation_decisions_metric_granularity_check
        check (
          metric_granularity is null
          or metric_granularity in (
            'competition', 'team', 'match', 'team_match', 'player_appearance',
            'player_match', 'player_season', 'goalkeeper_match', 'goalkeeper_season'
          )
        )
    `);
    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        drop constraint reconciliation_decisions_status_check
    `);
    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        add constraint reconciliation_decisions_status_check
        check (
          status in (
            'agreed', 'single_source', 'conflict', 'unresolved',
            'not_comparable', 'methodology_pending'
          )
        )
    `);
    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        drop constraint reconciliation_decisions_natural_key
    `);
    await tx.unsafe(`
      alter table ingestion.reconciliation_decisions
        add constraint reconciliation_decisions_natural_key
        unique nulls not distinct (
          logical_entity_key, metric_name, metric_granularity, model_version
        )
    `);
  });

  const after = await readDataMeshSchemaState();
  requireCondition(after.source_metric_granularity === true, "source metric_granularity missing after migration");
  requireCondition(after.decision_metric_granularity === true, "decision metric_granularity missing after migration");
  requireCondition(after.source_rows === 0 && after.decision_rows === 0, "Data Mesh rows changed during schema migration");
  requireCondition(
    after.source_natural_key?.includes("metric_granularity") &&
      after.source_natural_key?.includes("NULLS NOT DISTINCT"),
    "source V2 natural key verification failed",
  );
  requireCondition(
    after.decision_natural_key?.includes("metric_granularity") &&
      after.decision_natural_key?.includes("NULLS NOT DISTINCT"),
    "decision V2 natural key verification failed",
  );
  requireCondition(
    after.decision_status_check?.includes("methodology_pending") &&
      after.decision_status_check?.includes("not_comparable"),
    "decision V2 status verification failed",
  );
  console.log("DATA MESH V2 SCHEMA: PASS migrated exact canonical empty schema");
}

async function ensureWyscoutProviderSeed() {
  await sql.begin(async (tx) => {
    await tx`
      insert into ingestion.providers (code, display_name)
      values ('wyscout-open', 'Wyscout Open Data')
      on conflict (code) do update
      set
        display_name = excluded.display_name,
        is_active = true
    `;
  });
}

function requireCondition(condition, message) {
  if (!condition) throw new Error(`HISTORICAL PRODUCTION OPERATOR: ${message}`);
}

function run(command, args, cwd, label) {
  const result = spawnSync(command, args, {
    cwd,
    env: { ...process.env, UV_PYTHON: "3.13" },
    stdio: "inherit",
  });
  if (result.error) {
    throw new Error(`HISTORICAL PRODUCTION OPERATOR: ${label} could not start`);
  }
  if (result.status !== 0) {
    throw new Error(`HISTORICAL PRODUCTION OPERATOR: ${label} failed with status ${result.status}`);
  }
}

try {
  const before = await readProductionState();
  requireCondition(before.views.team_detail_v2 === "analytics.product_team_detail_v2", "team V2 view missing");
  requireCondition(before.views.player_detail_v2 === "analytics.product_player_detail_v2", "player V2 view missing");
  requireCondition(before.current.season_rows === 1, "ENG_PL 2025/26 season identity mismatch");
  requireCondition(before.current.matches === EXPECTED.currentMatches, "ENG_PL 2025/26 match count mismatch");
  requireCondition(before.current.team_match_stats === EXPECTED.currentTeamMatchStats, "ENG_PL 2025/26 team stats mismatch");
  requireCondition(before.safety.wyscout_provider_rows <= 1, "Wyscout provider seed is duplicated");
  requireCondition(before.safety.test_smoke_rows === 0, "test_smoke evidence found in production");

  const freshHistorical =
    before.historical.season_rows === 0 &&
    before.historical.matches === 0 &&
    before.historical.appearances === 0 &&
    before.historical.player_v2_scores === 0 &&
    before.historical.player_v2_features === 0 &&
    before.historical.source_observations === 0;

  const certifiedHistorical =
    before.historical.season_rows === 1 &&
    before.historical.matches === EXPECTED.historicalMatches &&
    before.historical.appearances === EXPECTED.historicalAppearances &&
    before.historical.player_v2_scores === EXPECTED.playerV2Scores &&
    before.historical.player_v2_features === EXPECTED.playerV2Features &&
    before.historical.source_observations === EXPECTED.historicalSourceObservations;

  requireCondition(
    freshHistorical || certifiedHistorical,
    `2017/18 is partial/unexpected: ${JSON.stringify(before.historical)}`,
  );
  console.log(`HISTORICAL PREWRITE STATE: ${freshHistorical ? "fresh" : "certified_complete"}`);

  await ensureDataMeshV2Schema();

  await ensureWyscoutProviderSeed();
  const seeded = await readProductionState();
  requireCondition(seeded.safety.wyscout_provider_rows === 1, "Wyscout provider seed upsert failed");
  requireCondition(
    JSON.stringify(seeded.historical) === JSON.stringify(before.historical),
    "historical scope changed while preparing production schema/catalog",
  );
  console.log("HISTORICAL PROVIDER SEED: PASS");

  const analyticsDir = path.resolve(process.cwd(), "../../analytics");
  const cacheDir = "/tmp/football-intelligence-wyscout-open";
  const reportPath = "/tmp/football-intelligence-historical-promotion.json";

  run("uv", ["sync", "--locked", "--python", "3.13"], analyticsDir, "uv sync");
  run(
    "uv",
    [
      "run",
      "--python",
      "3.13",
      "python",
      "-m",
      "football_intelligence.jobs.promote_historical_player_v2",
      "--cache-dir",
      cacheDir,
      "--database-url",
      databaseUrl,
      "--report",
      reportPath,
      "--allow-remote-write",
      "--confirm-target",
      "production",
      "--production-write-confirmation",
      "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE",
      "--confirm-database-target",
      safeTarget,
    ],
    analyticsDir,
    "historical promotion",
  );

  const report = JSON.parse(readFileSync(reportPath, "utf8"));
  requireCondition(report.status === "PASS", "promotion report did not PASS");
  requireCondition(report.production_written === true, "promotion report is not a production write");
  requireCondition(report.canonical.matches === EXPECTED.historicalMatches, "post-write match report mismatch");
  requireCondition(report.canonical.player_appearances === EXPECTED.historicalAppearances, "post-write appearance report mismatch");
  requireCondition(report.canonical.source_observations === EXPECTED.historicalSourceObservations, "post-write Data Mesh report mismatch");
  requireCondition(report.player_v2.score_snapshots === EXPECTED.playerV2Scores, "post-write Player V2 score report mismatch");
  requireCondition(report.player_v2.feature_snapshots === EXPECTED.playerV2Features, "post-write Player V2 feature report mismatch");

  const after = await readProductionState();
  requireCondition(after.historical.season_rows === 1, "2017/18 season missing after promotion");
  requireCondition(after.historical.matches === EXPECTED.historicalMatches, "2017/18 matches missing after promotion");
  requireCondition(after.historical.appearances === EXPECTED.historicalAppearances, "2017/18 appearances missing after promotion");
  requireCondition(after.historical.source_observations === EXPECTED.historicalSourceObservations, "2017/18 Data Mesh observations missing after promotion");
  requireCondition(after.historical.player_v2_scores === EXPECTED.playerV2Scores, "2017/18 Player V2 scores missing after promotion");
  requireCondition(after.historical.player_v2_features === EXPECTED.playerV2Features, "2017/18 Player V2 features missing after promotion");

  console.log("HISTORICAL PRODUCTION OPERATOR: PASS - certified Wyscout 2017/18 + Player V2 committed");
} finally {
  await sql.end({ timeout: 5 });
}
