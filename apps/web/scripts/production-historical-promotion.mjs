import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import postgres from "postgres";

const TARGET_COMPETITION = "ESP_LL";
const SEASON_LABEL = "2017/18";
const MODEL_VERSION = "player-v2.0";
const CONFIRMATION = "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE";

const SPECS = {
  ESP_LL: {
    providerCompetitionId: 795,
    matches: 380,
    teams: 20,
    players: 557,
    playerAppearances: 10555,
    playerMatchStats: 10555,
    teamMatchStats: 760,
    sourceObservations: 416407,
    playerV2Scores: 2224,
    playerV2Features: 29008,
    seasonPlayers: 556,
    seasonPlayers450Min: 415,
    performanceReady: 415,
  },
  FRA_L1: {
    providerCompetitionId: 412,
    matches: 380,
    teams: 20,
    players: 542,
    playerAppearances: 10515,
    playerMatchStats: 10515,
    teamMatchStats: 760,
    sourceObservations: 415230,
    playerV2Scores: 2148,
    playerV2Features: 28007,
    seasonPlayers: 537,
    seasonPlayers450Min: 395,
    performanceReady: 395,
  },
  GER_BL1: {
    providerCompetitionId: 426,
    matches: 306,
    teams: 18,
    players: 472,
    playerAppearances: 8501,
    playerMatchStats: 8501,
    teamMatchStats: 612,
    sourceObservations: 336265,
    playerV2Scores: 1888,
    playerV2Features: 24786,
    seasonPlayers: 472,
    seasonPlayers450Min: 349,
    performanceReady: 349,
  },
  ITA_SA: {
    providerCompetitionId: 524,
    matches: 380,
    teams: 20,
    players: 534,
    playerAppearances: 10573,
    playerMatchStats: 10573,
    teamMatchStats: 760,
    sourceObservations: 420506,
    playerV2Scores: 2132,
    playerV2Features: 27872,
    seasonPlayers: 533,
    seasonPlayers450Min: 403,
    performanceReady: 403,
  },
};

if (!process.env.VERCEL || process.env.VERCEL_ENV !== "production") {
  console.log(`HISTORICAL PRODUCTION PROMOTION: SKIP ${process.env.VERCEL_ENV ?? "non-vercel"}`);
  process.exit(0);
}

const originalDatabaseUrl = process.env.DATABASE_URL;
if (!originalDatabaseUrl) {
  throw new Error("HISTORICAL PRODUCTION PROMOTION: DATABASE_URL is missing");
}

const parsed = new URL(originalDatabaseUrl);
if (!parsed.port) parsed.port = "5432";
const databaseUrl = parsed.toString();
const databaseName = parsed.pathname.replace(/^\//, "") || "(default)";
const safeTarget = `postgresql://${parsed.hostname}:${parsed.port}/${databaseName}`;
const sql = postgres(databaseUrl, { max: 1, prepare: false });
const spec = SPECS[TARGET_COMPETITION];
const scopeKey = `competition:${TARGET_COMPETITION}:${SEASON_LABEL}`;

function requireCondition(condition, message) {
  if (!condition) throw new Error(`HISTORICAL PRODUCTION PROMOTION: ${message}`);
}

function run(command, args, cwd, label) {
  const result = spawnSync(command, args, {
    cwd,
    env: { ...process.env, UV_PYTHON: "3.13" },
    stdio: "inherit",
  });
  if (result.error) {
    throw new Error(`HISTORICAL PRODUCTION PROMOTION: ${label} could not start`);
  }
  if (result.status !== 0) {
    throw new Error(`HISTORICAL PRODUCTION PROMOTION: ${label} failed with status ${result.status}`);
  }
}

async function readScopeState(competitionCode, scopeSpec) {
  return sql.begin(async (tx) => {
    await tx.unsafe("SET TRANSACTION READ ONLY");
    const scope = `competition:${competitionCode}:${SEASON_LABEL}`;
    const [row] = await tx`
      with target_competition as (
        select id from football.competitions where code = ${competitionCode}
      ),
      target_season as (
        select s.id
        from football.seasons s
        where s.competition_id in (select id from target_competition)
          and s.label = ${SEASON_LABEL}
      )
      select
        (select count(*)::int from target_season) as season_rows,
        (select count(*)::int from football.matches m where m.season_id in (select id from target_season)) as matches,
        (select count(distinct team_id)::int from (
          select home_team_id as team_id from football.matches where season_id in (select id from target_season)
          union all
          select away_team_id as team_id from football.matches where season_id in (select id from target_season)
        ) scoped_teams) as teams,
        (select count(distinct pa.player_id)::int from football.player_appearances pa join football.matches m on m.id = pa.match_id where m.season_id in (select id from target_season)) as players,
        (select count(*)::int from football.player_appearances pa join football.matches m on m.id = pa.match_id where m.season_id in (select id from target_season)) as player_appearances,
        (select count(*)::int from football.player_match_stats pms join football.matches m on m.id = pms.match_id where m.season_id in (select id from target_season)) as player_match_stats,
        (select count(*)::int from football.team_match_stats tms join football.matches m on m.id = tms.match_id where m.season_id in (select id from target_season)) as team_match_stats,
        (select count(*)::int from ingestion.source_observations o join ingestion.providers p on p.id = o.provider_id where p.code = 'wyscout-open' and o.entity_identity_hints->>'season_label' = ${SEASON_LABEL} and o.entity_identity_hints->>'competition_external_id' = ${String(scopeSpec.providerCompetitionId)}) as source_observations,
        (select count(*)::int from analytics.player_score_snapshots where scope_key = ${scope} and model_version = ${MODEL_VERSION}) as player_v2_scores,
        (select count(*)::int from analytics.player_feature_snapshots where scope_key = ${scope} and model_version = ${MODEL_VERSION}) as player_v2_features,
        (select count(distinct player_id)::int from analytics.product_player_detail_v2 where scope_key = ${scope} and model_version = ${MODEL_VERSION} and window_key = 'season') as season_players,
        (select count(distinct player_id)::int from analytics.product_player_detail_v2 where scope_key = ${scope} and model_version = ${MODEL_VERSION} and window_key = 'season' and minutes >= 450) as season_players_450_min,
        (select count(*)::int from analytics.product_player_detail_v2 s cross join lateral jsonb_each(s.dimension_evidence) e where s.scope_key = ${scope} and s.model_version = ${MODEL_VERSION} and s.window_key = 'season' and e.key = 'performance' and e.value->>'evidence_state' = 'ready' and e.value->>'score' is not null) as performance_ready,
        (select count(*)::int from analytics.product_player_ranking_candidates_v2 where scope_key = ${scope} and model_version = ${MODEL_VERSION}) as ranking_candidates,
        (select count(*)::int from analytics.product_player_detail_v2 where scope_key = ${scope} and model_version = ${MODEL_VERSION} and overall_score is not null) as overall_scores
    `;
    return row;
  });
}

function isFresh(state) {
  return Object.values(state).every((value) => value === 0);
}

function assertCertified(state, scopeSpec, label) {
  const expected = {
    season_rows: 1,
    matches: scopeSpec.matches,
    teams: scopeSpec.teams,
    players: scopeSpec.players,
    player_appearances: scopeSpec.playerAppearances,
    player_match_stats: scopeSpec.playerMatchStats,
    team_match_stats: scopeSpec.teamMatchStats,
    source_observations: scopeSpec.sourceObservations,
    player_v2_scores: scopeSpec.playerV2Scores,
    player_v2_features: scopeSpec.playerV2Features,
    season_players: scopeSpec.seasonPlayers,
    season_players_450_min: scopeSpec.seasonPlayers450Min,
    performance_ready: scopeSpec.performanceReady,
    ranking_candidates: 0,
    overall_scores: 0,
  };
  requireCondition(JSON.stringify(state) === JSON.stringify(expected), `${label} mismatch: ${JSON.stringify(state)} != ${JSON.stringify(expected)}`);
}

async function readGlobalSafety() {
  return sql.begin(async (tx) => {
    await tx.unsafe("SET TRANSACTION READ ONLY");
    const [views] = await tx`
      select
        to_regclass('analytics.product_team_detail_v2')::text as team_detail_v2,
        to_regclass('analytics.product_player_detail_v2')::text as player_detail_v2,
        to_regclass('analytics.product_player_ranking_candidates_v2')::text as player_ranking_v2
    `;
    const [current] = await tx`
      with target_season as (
        select s.id from football.seasons s join football.competitions c on c.id = s.competition_id
        where c.code = 'ENG_PL' and s.label = '2025/26'
      )
      select
        (select count(*)::int from target_season) as season_rows,
        (select count(*)::int from football.matches where season_id in (select id from target_season)) as matches,
        (select count(*)::int from football.team_match_stats tms join football.matches m on m.id = tms.match_id where m.season_id in (select id from target_season)) as team_match_stats
    `;
    const [safety] = await tx`
      select
        (select count(*)::int from ingestion.providers where code = 'wyscout-open') as wyscout_provider_rows,
        (select count(*)::int from ingestion.source_observations where source_reference ilike '%test_smoke%') as test_smoke_rows
    `;
    return { views, current, safety };
  });
}

try {
  requireCondition(spec, `unknown target competition ${TARGET_COMPETITION}`);
  console.log(`HISTORICAL PRODUCTION PROMOTION TARGET: ${TARGET_COMPETITION} ${SEASON_LABEL}`);
  console.log(`HISTORICAL PRODUCTION PROMOTION DATABASE: ${safeTarget}`);

  const globalBefore = await readGlobalSafety();
  requireCondition(globalBefore.views.team_detail_v2 === "analytics.product_team_detail_v2", "team V2 view missing");
  requireCondition(globalBefore.views.player_detail_v2 === "analytics.product_player_detail_v2", "player V2 view missing");
  requireCondition(globalBefore.views.player_ranking_v2 === "analytics.product_player_ranking_candidates_v2", "player ranking V2 view missing");
  requireCondition(globalBefore.current.season_rows === 1, "ENG_PL 2025/26 season identity mismatch");
  requireCondition(globalBefore.current.matches === 380, "ENG_PL 2025/26 match count mismatch");
  requireCondition(globalBefore.current.team_match_stats === 760, "ENG_PL 2025/26 team stats mismatch");
  requireCondition(globalBefore.safety.wyscout_provider_rows === 1, "Wyscout provider seed is not unique");
  requireCondition(globalBefore.safety.test_smoke_rows === 0, "test_smoke evidence found in production");

  const before = await readScopeState(TARGET_COMPETITION, spec);
  if (isFresh(before)) {
    console.log(`HISTORICAL PRODUCTION PROMOTION PREWRITE: fresh for ${TARGET_COMPETITION}`);
    const analyticsDir = path.resolve(process.cwd(), "../../analytics");
    const cacheDir = "/tmp/football-intelligence-wyscout-open";
    const reportPath = `/tmp/football-intelligence-historical-promotion-${TARGET_COMPETITION}.json`;

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
        "--competition",
        TARGET_COMPETITION,
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
        CONFIRMATION,
        "--confirm-database-target",
        safeTarget,
      ],
      analyticsDir,
      `${TARGET_COMPETITION} historical promotion`,
    );

    const report = JSON.parse(readFileSync(reportPath, "utf8"));
    requireCondition(report.status === "PASS", "promotion report did not PASS");
    requireCondition(report.production_written === true, "promotion report is not a production write");
    requireCondition(report.competition === TARGET_COMPETITION, "promotion report competition mismatch");
    requireCondition(report.scope_key === scopeKey, "promotion report scope mismatch");
    requireCondition(report.canonical.matches === spec.matches, "promotion report match count mismatch");
    requireCondition(report.canonical.players === spec.players, "promotion report player count mismatch");
    requireCondition(report.canonical.source_observations === spec.sourceObservations, "promotion report source observation mismatch");
    requireCondition(report.player_v2.score_snapshots === spec.playerV2Scores, "promotion report score snapshot mismatch");
    requireCondition(report.player_v2.feature_snapshots === spec.playerV2Features, "promotion report feature snapshot mismatch");
    requireCondition(report.player_v2.season_players === spec.seasonPlayers, "promotion report season-player mismatch");
    requireCondition(report.player_v2.season_players_450_min === spec.seasonPlayers450Min, "promotion report 450-minute player mismatch");
    requireCondition(report.player_v2.performance_ready === spec.performanceReady, "promotion report performance-ready mismatch");
    requireCondition(report.player_v2.ranking_candidates === 0, "promotion unexpectedly created ranking candidates");
    requireCondition(report.player_v2.overall_scores === 0, "promotion unexpectedly created overall scores");
  } else {
    assertCertified(before, spec, "prewrite certified state");
    console.log(`HISTORICAL PRODUCTION PROMOTION PREWRITE: certified_complete; write skipped for ${TARGET_COMPETITION}`);
  }

  const after = await readScopeState(TARGET_COMPETITION, spec);
  assertCertified(after, spec, "postwrite independent SQL verification");
  const globalAfter = await readGlobalSafety();
  requireCondition(JSON.stringify(globalAfter) === JSON.stringify(globalBefore), "global production safety baseline changed unexpectedly");

  console.log(`HISTORICAL PRODUCTION PROMOTION: PASS ${TARGET_COMPETITION}`);
  console.log(`HISTORICAL PRODUCTION PROMOTION CERTIFIED STATE: ${JSON.stringify(after)}`);
} finally {
  await sql.end({ timeout: 5 });
}
