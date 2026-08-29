import { getDatabase } from "@/lib/db/postgres";

export interface MatchTeam {
  id: string;
  slug: string;
  name: string;
  shortName: string | null;
}

export interface MatchStatLine {
  teamId: string;
  goals: number | null;
  xg: number | null;
  shots: number | null;
  shotsOnTarget: number | null;
  possession: number | null;
  bigChances: number | null;
  boxTouches: number | null;
  corners: number | null;
  providerName: string | null;
  providerModel: string | null;
  extra: Record<string, unknown>;
}

export interface PublishedReviewBase {
  finalScore: number;
  factsScore: number | null;
  expertScore: number | null;
  fanScore: number | null;
  confidence: number;
  evidenceStatus: string;
  summary: string;
}

export interface MatchTeamReview extends PublishedReviewBase {
  teamId: string;
  teamName: string;
  attackScore: number | null;
  creationScore: number | null;
  controlScore: number | null;
  defenceScore: number | null;
  pressingScore: number | null;
  offensiveTransitionScore: number | null;
  defensiveTransitionScore: number | null;
  strengths: string[];
  concerns: string[];
}

export interface MatchManagerReview extends PublishedReviewBase {
  managerId: string;
  managerName: string;
  teamId: string;
  teamName: string;
  initialPlanScore: number | null;
  adaptationScore: number | null;
  substitutionsScore: number | null;
  initialPlan: string | null;
  adjustments: string | null;
  whatWorked: string[];
  whatFailed: string[];
}

export interface MatchPlayerReview extends PublishedReviewBase {
  playerId: string;
  playerName: string;
  teamId: string;
  teamName: string;
  starter: boolean | null;
  minutes: number | null;
  roleLabel: string | null;
  positiveNotes: string[];
  negativeNotes: string[];
  providerRating: number | null;
  goals: number | null;
  assists: number | null;
  xg: number | null;
  shots: number | null;
  shotsOnTarget: number | null;
}

export interface MatchSource {
  id: string;
  sourceName: string;
  title: string | null;
  url: string;
  author: string | null;
  documentType: string;
}

export interface MatchDetailData {
  id: string;
  kickoffAt: string;
  competition: string;
  season: string;
  round: string | null;
  venue: string | null;
  attendance: number | null;
  referee: string | null;
  homeGoals: number;
  awayGoals: number;
  home: MatchTeam;
  away: MatchTeam;
  stats: MatchStatLine[];
  reading: string;
  takeaways: string[];
  teamReviews: MatchTeamReview[];
  managerReviews: MatchManagerReview[];
  playerReviews: MatchPlayerReview[];
  sources: MatchSource[];
}

export type MatchDetailResult =
  | { status: "ready"; data: MatchDetailData | null }
  | { status: "unconfigured"; message: string }
  | { status: "error"; message: string };

interface DbMatchRow {
  id: string;
  kickoff_at: Date | string;
  competition_name: string;
  season_label: string;
  round_label: string | null;
  venue: string | null;
  attendance: string | number | null;
  referee: string | null;
  home_goals: string | number;
  away_goals: string | number;
  home_team_id: string;
  home_slug: string;
  home_name: string;
  home_short_name: string | null;
  away_team_id: string;
  away_slug: string;
  away_name: string;
  away_short_name: string | null;
  reading: string;
  key_takeaways: unknown;
  evidence_mix: unknown;
}

interface DbStatRow {
  team_id: string;
  goals: string | number | null;
  xg: string | number | null;
  shots: string | number | null;
  shots_on_target: string | number | null;
  possession_pct: string | number | null;
  big_chances: string | number | null;
  box_touches: string | number | null;
  corners: string | number | null;
  provider_name: string | null;
  provider_model: string | null;
  extra_stats: unknown;
}

interface DbTeamReviewRow {
  team_id: string;
  team_name: string;
  final_score: string | number;
  facts_score: string | number | null;
  expert_score: string | number | null;
  fan_score: string | number | null;
  confidence: string | number;
  evidence_status: string;
  summary: string;
  attack_score: string | number | null;
  creation_score: string | number | null;
  control_score: string | number | null;
  defence_score: string | number | null;
  pressing_score: string | number | null;
  offensive_transition_score: string | number | null;
  defensive_transition_score: string | number | null;
  strengths: unknown;
  concerns: unknown;
}

interface DbManagerReviewRow {
  manager_id: string;
  manager_name: string;
  team_id: string;
  team_name: string;
  final_score: string | number;
  facts_score: string | number | null;
  expert_score: string | number | null;
  fan_score: string | number | null;
  confidence: string | number;
  evidence_status: string;
  summary: string;
  initial_plan_score: string | number | null;
  adaptation_score: string | number | null;
  substitutions_score: string | number | null;
  initial_plan: string | null;
  adjustments: string | null;
  what_worked: unknown;
  what_failed: unknown;
}

interface DbPlayerReviewRow {
  player_id: string;
  player_name: string;
  team_id: string;
  team_name: string;
  starter: boolean | null;
  minutes: string | number | null;
  role_label: string | null;
  final_score: string | number;
  facts_score: string | number | null;
  expert_score: string | number | null;
  fan_score: string | number | null;
  confidence: string | number;
  evidence_status: string;
  summary: string;
  positive_notes: unknown;
  negative_notes: unknown;
  provider_rating: string | number | null;
  goals: string | number | null;
  assists: string | number | null;
  xg: string | number | null;
  shots: string | number | null;
  shots_on_target: string | number | null;
}

interface DbSourceRow {
  id: string;
  source_name: string;
  title: string | null;
  url: string;
  author_text: string | null;
  document_type: string;
}

const numeric = (value: string | number): number => Number(value);
const nullableNumeric = (value: string | number | null): number | null =>
  value === null ? null : Number(value);
const stringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const objectValue = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
const isoValue = (value: Date | string): string =>
  value instanceof Date ? value.toISOString() : new Date(value).toISOString();

function sourceDocumentIds(evidenceMix: unknown): string[] {
  const mix = objectValue(evidenceMix);
  return stringArray(mix.source_document_ids);
}

export async function getMatchDetail(matchId: string): Promise<MatchDetailResult> {
  const sql = getDatabase();
  if (!sql) {
    return {
      status: "unconfigured",
      message: "DATABASE_URL no está configurada. La página de partido leerá PostgreSQL cuando exista conexión.",
    };
  }

  try {
    const matchRows = await sql<DbMatchRow[]>`
      select
        m.id,
        m.kickoff_at,
        c.name as competition_name,
        s.label as season_label,
        r.label as round_label,
        m.venue,
        m.attendance,
        m.referee,
        m.home_goals,
        m.away_goals,
        home.id as home_team_id,
        home.slug as home_slug,
        home.name as home_name,
        home.short_name as home_short_name,
        away.id as away_team_id,
        away.slug as away_slug,
        away.name as away_name,
        away.short_name as away_short_name,
        mr.summary as reading,
        mr.key_takeaways,
        mr.evidence_mix
      from public.matches m
      join public.seasons s on s.id = m.season_id
      join public.competitions c on c.id = s.competition_id
      join public.teams home on home.id = m.home_team_id
      join public.teams away on away.id = m.away_team_id
      left join public.rounds r on r.id = m.round_id
      join public.v_current_match_reviews mr on mr.match_id = m.id
      where m.id = ${matchId}::uuid
        and m.identity_verified = true
      limit 1
    `;

    const match = matchRows[0];
    if (!match) return { status: "ready", data: null };

    const [statRows, teamRows, managerRows, playerRows] = await Promise.all([
      sql<DbStatRow[]>`
        select
          tms.team_id,
          tms.goals,
          tms.xg,
          tms.shots,
          tms.shots_on_target,
          tms.possession_pct,
          tms.big_chances,
          tms.box_touches,
          tms.corners,
          src.name as provider_name,
          tms.provider_model,
          tms.extra_stats
        from public.team_match_stats tms
        left join public.sources src on src.id = tms.provider_source_id
        where tms.match_id = ${matchId}::uuid
        order by tms.retrieved_at desc
      `,
      sql<DbTeamReviewRow[]>`
        select r.*, t.name as team_name
        from public.v_current_team_match_reviews r
        join public.teams t on t.id = r.team_id
        where r.match_id = ${matchId}::uuid
        order by case when r.team_id = ${match.home_team_id}::uuid then 0 else 1 end
      `,
      sql<DbManagerReviewRow[]>`
        select r.*, m.display_name as manager_name, t.name as team_name
        from public.v_current_manager_match_reviews r
        join public.managers m on m.id = r.manager_id
        join public.teams t on t.id = r.team_id
        where r.match_id = ${matchId}::uuid
        order by case when r.team_id = ${match.home_team_id}::uuid then 0 else 1 end
      `,
      sql<DbPlayerReviewRow[]>`
        select
          r.player_id,
          p.display_name as player_name,
          r.team_id,
          t.name as team_name,
          a.starter,
          a.minutes,
          coalesce(r.role_label, a.role_label, a.broad_position) as role_label,
          r.final_score,
          r.facts_score,
          r.expert_score,
          r.fan_score,
          r.confidence,
          r.evidence_status,
          r.summary,
          r.positive_notes,
          r.negative_notes,
          case when (pms.extra_stats ->> 'provider_rating') ~ '^[0-9]+(\\.[0-9]+)?$'
            then (pms.extra_stats ->> 'provider_rating')::numeric else null end as provider_rating,
          pms.goals,
          pms.assists,
          pms.xg,
          pms.shots,
          pms.shots_on_target
        from public.v_current_player_match_reviews r
        join public.players p on p.id = r.player_id
        join public.teams t on t.id = r.team_id
        left join public.player_appearances a on a.match_id = r.match_id and a.player_id = r.player_id
        left join lateral (
          select ps.*
          from public.player_match_stats ps
          where ps.match_id = r.match_id and ps.player_id = r.player_id
          order by ps.retrieved_at desc
          limit 1
        ) pms on true
        where r.match_id = ${matchId}::uuid
        order by
          case when r.team_id = ${match.home_team_id}::uuid then 0 else 1 end,
          r.final_score desc,
          p.display_name
      `,
    ]);

    const sourceIds = sourceDocumentIds(match.evidence_mix);
    const sourceRows = sourceIds.length
      ? await sql<DbSourceRow[]>`
          select sd.id, s.name as source_name, sd.title, sd.url, sd.author_text, sd.document_type
          from public.source_documents sd
          join public.sources s on s.id = sd.source_id
          where sd.id in ${sql(sourceIds)}
          order by s.name, sd.title nulls last
        `
      : [];

    return {
      status: "ready",
      data: {
        id: match.id,
        kickoffAt: isoValue(match.kickoff_at),
        competition: match.competition_name,
        season: match.season_label,
        round: match.round_label,
        venue: match.venue,
        attendance: match.attendance === null ? null : numeric(match.attendance),
        referee: match.referee,
        homeGoals: numeric(match.home_goals),
        awayGoals: numeric(match.away_goals),
        home: {
          id: match.home_team_id,
          slug: match.home_slug,
          name: match.home_name,
          shortName: match.home_short_name,
        },
        away: {
          id: match.away_team_id,
          slug: match.away_slug,
          name: match.away_name,
          shortName: match.away_short_name,
        },
        stats: statRows.map((row) => ({
          teamId: row.team_id,
          goals: nullableNumeric(row.goals),
          xg: nullableNumeric(row.xg),
          shots: nullableNumeric(row.shots),
          shotsOnTarget: nullableNumeric(row.shots_on_target),
          possession: nullableNumeric(row.possession_pct),
          bigChances: nullableNumeric(row.big_chances),
          boxTouches: nullableNumeric(row.box_touches),
          corners: nullableNumeric(row.corners),
          providerName: row.provider_name,
          providerModel: row.provider_model,
          extra: objectValue(row.extra_stats),
        })),
        reading: match.reading,
        takeaways: stringArray(match.key_takeaways),
        teamReviews: teamRows.map((row) => ({
          teamId: row.team_id,
          teamName: row.team_name,
          finalScore: numeric(row.final_score),
          factsScore: nullableNumeric(row.facts_score),
          expertScore: nullableNumeric(row.expert_score),
          fanScore: nullableNumeric(row.fan_score),
          confidence: numeric(row.confidence),
          evidenceStatus: row.evidence_status,
          summary: row.summary,
          attackScore: nullableNumeric(row.attack_score),
          creationScore: nullableNumeric(row.creation_score),
          controlScore: nullableNumeric(row.control_score),
          defenceScore: nullableNumeric(row.defence_score),
          pressingScore: nullableNumeric(row.pressing_score),
          offensiveTransitionScore: nullableNumeric(row.offensive_transition_score),
          defensiveTransitionScore: nullableNumeric(row.defensive_transition_score),
          strengths: stringArray(row.strengths),
          concerns: stringArray(row.concerns),
        })),
        managerReviews: managerRows.map((row) => ({
          managerId: row.manager_id,
          managerName: row.manager_name,
          teamId: row.team_id,
          teamName: row.team_name,
          finalScore: numeric(row.final_score),
          factsScore: nullableNumeric(row.facts_score),
          expertScore: nullableNumeric(row.expert_score),
          fanScore: nullableNumeric(row.fan_score),
          confidence: numeric(row.confidence),
          evidenceStatus: row.evidence_status,
          summary: row.summary,
          initialPlanScore: nullableNumeric(row.initial_plan_score),
          adaptationScore: nullableNumeric(row.adaptation_score),
          substitutionsScore: nullableNumeric(row.substitutions_score),
          initialPlan: row.initial_plan,
          adjustments: row.adjustments,
          whatWorked: stringArray(row.what_worked),
          whatFailed: stringArray(row.what_failed),
        })),
        playerReviews: playerRows.map((row) => ({
          playerId: row.player_id,
          playerName: row.player_name,
          teamId: row.team_id,
          teamName: row.team_name,
          starter: row.starter,
          minutes: nullableNumeric(row.minutes),
          roleLabel: row.role_label,
          finalScore: numeric(row.final_score),
          factsScore: nullableNumeric(row.facts_score),
          expertScore: nullableNumeric(row.expert_score),
          fanScore: nullableNumeric(row.fan_score),
          confidence: numeric(row.confidence),
          evidenceStatus: row.evidence_status,
          summary: row.summary,
          positiveNotes: stringArray(row.positive_notes),
          negativeNotes: stringArray(row.negative_notes),
          providerRating: nullableNumeric(row.provider_rating),
          goals: nullableNumeric(row.goals),
          assists: nullableNumeric(row.assists),
          xg: nullableNumeric(row.xg),
          shots: nullableNumeric(row.shots),
          shotsOnTarget: nullableNumeric(row.shots_on_target),
        })),
        sources: sourceRows.map((row) => ({
          id: row.id,
          sourceName: row.source_name,
          title: row.title,
          url: row.url,
          author: row.author_text,
          documentType: row.document_type,
        })),
      },
    };
  } catch {
    return { status: "error", message: "No se pudo leer el partido publicado." };
  }
}
