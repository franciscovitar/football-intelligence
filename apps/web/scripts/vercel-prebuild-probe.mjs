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
  requireCondition(before.safety.wyscout_provider_rows === 1, "Wyscout provider seed missing or duplicated");
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
