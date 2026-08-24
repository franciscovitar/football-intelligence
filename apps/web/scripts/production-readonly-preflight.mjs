import postgres from "postgres";

const TARGETS = [
  {
    competitionCode: "ESP_LL",
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
  },
  {
    competitionCode: "FRA_L1",
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
  },
  {
    competitionCode: "GER_BL1",
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
  },
  {
    competitionCode: "ITA_SA",
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
  },
];

const CERTIFIED_ENG = {
  competitionCode: "ENG_PL",
  providerCompetitionId: 364,
  matches: 380,
  teams: 20,
  players: 515,
  playerAppearances: 10443,
  playerMatchStats: 10443,
  teamMatchStats: 760,
  sourceObservations: 412609,
  playerV2Scores: 2048,
  playerV2Features: 26841,
};

const SEASON_LABEL = "2017/18";
const MODEL_VERSION = "player-v2.0";

class IntentionalReadonlyRollback extends Error {}

function requireCondition(condition, message) {
  if (!condition) throw new Error(`PRODUCTION READONLY PREFLIGHT: ${message}`);
}

function isFresh(state) {
  return (
    state.seasonRows === 0 &&
    state.matches === 0 &&
    state.teams === 0 &&
    state.players === 0 &&
    state.playerAppearances === 0 &&
    state.playerMatchStats === 0 &&
    state.teamMatchStats === 0 &&
    state.sourceObservations === 0 &&
    state.playerV2Scores === 0 &&
    state.playerV2Features === 0
  );
}

function isCertifiedComplete(state, spec) {
  return (
    state.seasonRows === 1 &&
    state.matches === spec.matches &&
    state.teams === spec.teams &&
    state.players === spec.players &&
    state.playerAppearances === spec.playerAppearances &&
    state.playerMatchStats === spec.playerMatchStats &&
    state.teamMatchStats === spec.teamMatchStats &&
    state.sourceObservations === spec.sourceObservations &&
    state.playerV2Scores === spec.playerV2Scores &&
    state.playerV2Features === spec.playerV2Features
  );
}

async function readHistoricalScope(tx, spec) {
  const competitionRows = await tx`
    select id
    from football.competitions
    where code = ${spec.competitionCode}
  `;
  requireCondition(
    competitionRows.length === 1,
    `${spec.competitionCode} competition seed count=${competitionRows.length}`,
  );

  const competitionId = competitionRows[0].id;
  const seasonRows = await tx`
    select id
    from football.seasons
    where competition_id = ${competitionId}
      and label = ${SEASON_LABEL}
  `;
  requireCondition(
    seasonRows.length <= 1,
    `${spec.competitionCode} ${SEASON_LABEL} has duplicate season rows`,
  );

  let matches = 0;
  let teams = 0;
  let players = 0;
  let playerAppearances = 0;
  let playerMatchStats = 0;
  let teamMatchStats = 0;

  if (seasonRows.length === 1) {
    const seasonId = seasonRows[0].id;
    const [canonical] = await tx`
      select
        (select count(*)::int from football.matches m where m.season_id = ${seasonId}) as matches,
        (
          select count(distinct team_id)::int
          from (
            select home_team_id as team_id from football.matches where season_id = ${seasonId}
            union all
            select away_team_id as team_id from football.matches where season_id = ${seasonId}
          ) scoped
        ) as teams,
        (
          select count(distinct pa.player_id)::int
          from football.player_appearances pa
          join football.matches m on m.id = pa.match_id
          where m.season_id = ${seasonId}
        ) as players,
        (
          select count(*)::int
          from football.player_appearances pa
          join football.matches m on m.id = pa.match_id
          where m.season_id = ${seasonId}
        ) as player_appearances,
        (
          select count(*)::int
          from football.player_match_stats pms
          join football.matches m on m.id = pms.match_id
          where m.season_id = ${seasonId}
        ) as player_match_stats,
        (
          select count(*)::int
          from football.team_match_stats tms
          join football.matches m on m.id = tms.match_id
          where m.season_id = ${seasonId}
        ) as team_match_stats
    `;
    matches = canonical.matches;
    teams = canonical.teams;
    players = canonical.players;
    playerAppearances = canonical.player_appearances;
    playerMatchStats = canonical.player_match_stats;
    teamMatchStats = canonical.team_match_stats;
  }

  const [external] = await tx`
    select
      (
        select count(*)::int
        from ingestion.source_observations o
        join ingestion.providers p on p.id = o.provider_id
        where p.code = 'wyscout-open'
          and o.entity_identity_hints ->> 'season_label' = ${SEASON_LABEL}
          and o.entity_identity_hints ->> 'competition_external_id' = ${String(spec.providerCompetitionId)}
      ) as source_observations,
      (
        select count(*)::int
        from analytics.player_score_snapshots
        where scope_key = ${`competition:${spec.competitionCode}:${SEASON_LABEL}`}
          and model_version = ${MODEL_VERSION}
      ) as player_v2_scores,
      (
        select count(*)::int
        from analytics.player_feature_snapshots
        where scope_key = ${`competition:${spec.competitionCode}:${SEASON_LABEL}`}
          and model_version = ${MODEL_VERSION}
      ) as player_v2_features
  `;

  return {
    seasonRows: seasonRows.length,
    matches,
    teams,
    players,
    playerAppearances,
    playerMatchStats,
    teamMatchStats,
    sourceObservations: external.source_observations,
    playerV2Scores: external.player_v2_scores,
    playerV2Features: external.player_v2_features,
  };
}

if (!process.env.VERCEL || process.env.VERCEL_ENV !== "production") {
  console.log(`PRODUCTION READONLY PREFLIGHT: SKIP ${process.env.VERCEL_ENV ?? "non-vercel"}`);
  process.exit(0);
}

const originalDatabaseUrl = process.env.DATABASE_URL;
if (!originalDatabaseUrl) {
  throw new Error("PRODUCTION READONLY PREFLIGHT: DATABASE_URL is missing");
}

const parsed = new URL(originalDatabaseUrl);
if (!parsed.port) parsed.port = "5432";
const databaseUrl = parsed.toString();
const databaseName = parsed.pathname.replace(/^\//, "") || "(default)";
const safeTarget = `postgresql://${parsed.hostname}:${parsed.port}/${databaseName}`;

const sql = postgres(databaseUrl, { max: 1, prepare: false });
let report;

try {
  try {
    await sql.begin(async (tx) => {
      await tx.unsafe("SET TRANSACTION READ ONLY");

      const [views] = await tx`
        select
          to_regclass('analytics.product_team_detail_v2')::text as team_detail_v2,
          to_regclass('analytics.product_player_detail_v2')::text as player_detail_v2,
          to_regclass('analytics.product_player_ranking_candidates_v2')::text as ranking_candidates_v2
      `;
      requireCondition(
        views.team_detail_v2 === "analytics.product_team_detail_v2",
        "team V2 product view missing",
      );
      requireCondition(
        views.player_detail_v2 === "analytics.product_player_detail_v2",
        "player V2 product view missing",
      );
      requireCondition(
        views.ranking_candidates_v2 === "analytics.product_player_ranking_candidates_v2",
        "player ranking candidates V2 view missing",
      );

      const [schema] = await tx`
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
      requireCondition(schema.source_metric_granularity === true, "source metric_granularity missing");
      requireCondition(schema.decision_metric_granularity === true, "decision metric_granularity missing");
      requireCondition(
        schema.source_natural_key?.includes("metric_granularity") &&
          schema.source_natural_key?.includes("NULLS NOT DISTINCT"),
        "source_observations V2 natural key is not canonical",
      );
      requireCondition(
        schema.decision_natural_key?.includes("metric_granularity") &&
          schema.decision_natural_key?.includes("NULLS NOT DISTINCT"),
        "reconciliation_decisions V2 natural key is not canonical",
      );
      requireCondition(
        schema.decision_status_check?.includes("methodology_pending") &&
          schema.decision_status_check?.includes("not_comparable"),
        "reconciliation_decisions V2 status vocabulary is not canonical",
      );

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
          (
            select count(*)::int
            from football.team_match_stats tms
            join football.matches m on m.id = tms.match_id
            where m.season_id in (select id from target_season)
          ) as team_match_stats
      `;
      requireCondition(current.season_rows === 1, "ENG_PL 2025/26 season identity mismatch");
      requireCondition(current.matches === 380, "ENG_PL 2025/26 match count mismatch");
      requireCondition(current.team_match_stats === 760, "ENG_PL 2025/26 team stats mismatch");

      const [safety] = await tx`
        select
          (select count(*)::int from ingestion.providers where code='wyscout-open') as wyscout_provider_rows,
          (select count(*)::int from ingestion.source_observations where source_reference ilike '%test_smoke%') as test_smoke_rows
      `;
      requireCondition(safety.wyscout_provider_rows === 1, "Wyscout provider seed count mismatch");
      requireCondition(safety.test_smoke_rows === 0, "test_smoke evidence found in production");

      const engState = await readHistoricalScope(tx, CERTIFIED_ENG);
      requireCondition(
        isCertifiedComplete(engState, CERTIFIED_ENG),
        `ENG_PL 2017/18 certified scope drifted: ${JSON.stringify(engState)}`,
      );

      const targets = {};
      for (const spec of TARGETS) {
        const state = await readHistoricalScope(tx, spec);
        const prewriteState = isFresh(state)
          ? "fresh"
          : isCertifiedComplete(state, spec)
            ? "certified_complete"
            : "partial_or_unexpected";
        requireCondition(
          prewriteState !== "partial_or_unexpected",
          `${spec.competitionCode} 2017/18 partial/unexpected: ${JSON.stringify(state)}`,
        );
        targets[spec.competitionCode] = { prewriteState, ...state };
      }

      report = {
        status: "PASS",
        target: safeTarget,
        transaction: "READ ONLY; intentional rollback",
        views: "PASS",
        dataMeshV2Schema: "PASS",
        currentEngPl2025_26: current,
        safety,
        certifiedEngPl2017_18: engState,
        targets,
      };

      throw new IntentionalReadonlyRollback("intentional rollback after successful read-only preflight");
    });
  } catch (error) {
    if (!(error instanceof IntentionalReadonlyRollback)) throw error;
  }

  requireCondition(report?.status === "PASS", "report was not produced");
  console.log(`PRODUCTION READONLY PREFLIGHT TARGET: ${safeTarget}`);
  console.log(`PRODUCTION READONLY PREFLIGHT REPORT: ${JSON.stringify(report)}`);
  console.log("PRODUCTION READONLY PREFLIGHT ROLLBACK: PASS");
  console.log("PRODUCTION READONLY PREFLIGHT: PASS");
} finally {
  await sql.end({ timeout: 5 });
}
