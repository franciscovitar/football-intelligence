import { execFileSync } from "node:child_process";
import postgres from "postgres";

if (!process.env.VERCEL) {
  console.log("VERCEL PREFLIGHT PROBE: SKIP outside Vercel");
  process.exit(0);
}

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  console.log(`VERCEL PREFLIGHT PROBE: SKIP ${process.env.VERCEL_ENV ?? "unknown"} without DATABASE_URL`);
  process.exit(0);
}

const parsed = new URL(databaseUrl);
const port = parsed.port ? `:${parsed.port}` : "";
const databaseName = parsed.pathname.replace(/^\//, "") || "(default)";
console.log(`VERCEL SAFE DATABASE TARGET: postgresql://${parsed.hostname}${port}/${databaseName}`);
console.log(`VERCEL ENVIRONMENT: ${process.env.VERCEL_ENV ?? "unknown"}`);

for (const [label, command, args] of [
  ["python3", "python3", ["--version"]],
  ["python3.13", "python3.13", ["--version"]],
  ["uv", "uv", ["--version"]],
]) {
  try {
    const output = execFileSync(command, args, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    console.log(`RUNTIME ${label}: ${output.trim()}`);
  } catch {
    console.log(`RUNTIME ${label}: unavailable`);
  }
}

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  await sql.begin(async (tx) => {
    await tx.unsafe("SET TRANSACTION READ ONLY");

    const [views] = await tx`
      select
        to_regclass('analytics.product_team_detail_v2')::text as team_detail_v2,
        to_regclass('analytics.product_player_detail_v2')::text as player_detail_v2
    `;
    console.log(`VIEW team_detail_v2: ${views.team_detail_v2 ?? "missing"}`);
    console.log(`VIEW player_detail_v2: ${views.player_detail_v2 ?? "missing"}`);

    const [scope] = await tx`
      select
        count(*) filter (where s.label = '2025/26')::int as seasons_2025_26,
        count(*) filter (where s.label = '2017/18')::int as seasons_2017_18
      from football.seasons s
      join football.competitions c on c.id = s.competition_id
      where c.code = 'ENG_PL'
    `;
    console.log(`ENG_PL 2025/26 season rows: ${scope.seasons_2025_26}`);
    console.log(`ENG_PL 2017/18 season rows: ${scope.seasons_2017_18}`);

    const [historical] = await tx`
      with target_season as (
        select s.id
        from football.seasons s
        join football.competitions c on c.id = s.competition_id
        where c.code = 'ENG_PL' and s.label = '2017/18'
      )
      select
        (select count(*)::int from football.matches m where m.season_id in (select id from target_season)) as matches,
        (select count(*)::int from football.player_appearances pa join football.matches m on m.id = pa.match_id where m.season_id in (select id from target_season)) as appearances,
        (select count(*)::int from analytics.player_score_snapshots ps where ps.scope_key = 'competition:ENG_PL:2017/18' and ps.model_version = 'player-v2.0') as player_v2_scores
    `;
    console.log(`ENG_PL 2017/18 matches: ${historical.matches}`);
    console.log(`ENG_PL 2017/18 appearances: ${historical.appearances}`);
    console.log(`ENG_PL 2017/18 Player V2 scores: ${historical.player_v2_scores}`);
  });
} finally {
  await sql.end({ timeout: 5 });
}

console.log("VERCEL PREFLIGHT PROBE: PASS READ ONLY");

if (process.env.VERCEL_ENV === "production") {
  throw new Error("INTENTIONAL STOP AFTER READ-ONLY PRODUCTION PREFLIGHT");
}
