import { getDatabase } from "@/lib/db/postgres";
import type { DataResult } from "@/lib/queries/player-analytics";

export type PerceptionSourceKind = "expert" | "media" | "fan" | "other";

export interface PerceptionLinkedPlayer {
  playerId: number;
  playerName: string;
}

export interface PerceptionEvidence {
  evidenceId: number;
  sourceCode: string;
  sourceName: string;
  sourceKind: PerceptionSourceKind;
  canonicalUrl: string;
  title: string;
  excerpt: string | null;
  publishedAt: string | null;
  discoveredAt: string;
  linkedPlayers: PerceptionLinkedPlayer[];
}

export interface PerceptionSourceSummary {
  sourceCode: string;
  sourceName: string;
  sourceKind: PerceptionSourceKind;
  homepageUrl: string | null;
  uniqueEvidenceCount: number;
  lastPublishedAt: string | null;
}

export interface PerceptionFilters {
  kind: PerceptionSourceKind | "all";
  search: string;
}

export interface PerceptionPageData {
  sources: PerceptionSourceSummary[];
  evidence: PerceptionEvidence[];
}

interface DbEvidenceRow {
  id: string | number;
  source_code: string;
  source_name: string;
  source_kind: PerceptionSourceKind;
  canonical_url: string;
  title: string;
  excerpt: string | null;
  published_at: Date | string | null;
  discovered_at: Date | string;
  linked_players: unknown;
}

interface DbSourceSummaryRow {
  source_code: string;
  source_name: string;
  source_kind: PerceptionSourceKind;
  homepage_url: string | null;
  unique_evidence_count: string | number;
  last_published_at: Date | string | null;
}

function isoValue(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function nullableIso(value: Date | string | null): string | null {
  return value === null ? null : isoValue(value);
}

function mapLinkedPlayers(value: unknown): PerceptionLinkedPlayer[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (
      typeof item !== "object" ||
      item === null ||
      !("playerId" in item) ||
      !("playerName" in item)
    ) {
      return [];
    }
    const candidate = item as { playerId: unknown; playerName: unknown };
    const playerId = Number(candidate.playerId);
    if (!Number.isSafeInteger(playerId) || typeof candidate.playerName !== "string") {
      return [];
    }
    return [{ playerId, playerName: candidate.playerName }];
  });
}

function mapEvidence(row: DbEvidenceRow): PerceptionEvidence {
  return {
    evidenceId: Number(row.id),
    sourceCode: row.source_code,
    sourceName: row.source_name,
    sourceKind: row.source_kind,
    canonicalUrl: row.canonical_url,
    title: row.title,
    excerpt: row.excerpt,
    publishedAt: nullableIso(row.published_at),
    discoveredAt: isoValue(row.discovered_at),
    linkedPlayers: mapLinkedPlayers(row.linked_players),
  };
}

function unconfigured<T>(): DataResult<T> {
  return {
    status: "unconfigured",
    message:
      "DATABASE_URL no está configurada. Perception Intelligence leerá PostgreSQL cuando exista conexión.",
  };
}

function failed<T>(): DataResult<T> {
  return {
    status: "error",
    message: "No se pudo leer la evidencia de Perception Intelligence.",
  };
}

export async function getPerceptionPage(
  filters: PerceptionFilters,
): Promise<DataResult<PerceptionPageData>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const searchPattern = `%${filters.search.trim()}%`;
    const sources = await sql<DbSourceSummaryRow[]>`
      select
        s.code as source_code,
        s.display_name as source_name,
        s.source_kind,
        s.homepage_url,
        count(e.id) filter (where e.duplicate_of_id is null) as unique_evidence_count,
        max(e.published_at) filter (where e.duplicate_of_id is null) as last_published_at
      from perception.sources as s
      left join perception.evidence_items as e on e.source_id = s.id
      where s.is_active
        and (${filters.kind} = 'all' or s.source_kind = ${filters.kind})
      group by s.id
      order by s.source_kind, s.display_name
    `;

    const evidence = await sql<DbEvidenceRow[]>`
      select
        e.id,
        s.code as source_code,
        s.display_name as source_name,
        s.source_kind,
        e.canonical_url,
        e.title,
        e.excerpt,
        e.published_at,
        e.discovered_at,
        coalesce(
          (
            select jsonb_agg(
              jsonb_build_object(
                'playerId', p.id,
                'playerName', p.display_name
              )
              order by p.display_name
            )
            from perception.player_evidence_mentions as m
            join football.players as p on p.id = m.player_id
            where m.evidence_id = e.id
          ),
          '[]'::jsonb
        ) as linked_players
      from perception.evidence_items as e
      join perception.sources as s on s.id = e.source_id
      where e.duplicate_of_id is null
        and s.is_active
        and (${filters.kind} = 'all' or s.source_kind = ${filters.kind})
        and (
          ${filters.search.trim()} = ''
          or e.title ilike ${searchPattern}
          or coalesce(e.excerpt, '') ilike ${searchPattern}
          or exists (
            select 1
            from perception.player_evidence_mentions as m
            join football.players as p on p.id = m.player_id
            where m.evidence_id = e.id
              and p.display_name ilike ${searchPattern}
          )
        )
      order by e.published_at desc nulls last, e.discovered_at desc, e.id desc
      limit 100
    `;

    return {
      status: "ready",
      data: {
        sources: sources.map((row) => ({
          sourceCode: row.source_code,
          sourceName: row.source_name,
          sourceKind: row.source_kind,
          homepageUrl: row.homepage_url,
          uniqueEvidenceCount: Number(row.unique_evidence_count),
          lastPublishedAt: nullableIso(row.last_published_at),
        })),
        evidence: evidence.map(mapEvidence),
      },
    };
  } catch {
    return failed();
  }
}

export async function getPlayerPerceptionEvidence(
  playerId: number,
): Promise<DataResult<PerceptionEvidence[]>> {
  const sql = getDatabase();
  if (!sql) return unconfigured();

  try {
    const rows = await sql<DbEvidenceRow[]>`
      select
        e.id,
        s.code as source_code,
        s.display_name as source_name,
        s.source_kind,
        e.canonical_url,
        e.title,
        e.excerpt,
        e.published_at,
        e.discovered_at,
        coalesce(
          (
            select jsonb_agg(
              jsonb_build_object(
                'playerId', p.id,
                'playerName', p.display_name
              )
              order by p.display_name
            )
            from perception.player_evidence_mentions as linked
            join football.players as p on p.id = linked.player_id
            where linked.evidence_id = e.id
          ),
          '[]'::jsonb
        ) as linked_players
      from perception.player_evidence_mentions as mention
      join perception.evidence_items as e on e.id = mention.evidence_id
      join perception.sources as s on s.id = e.source_id
      where mention.player_id = ${playerId}
        and e.duplicate_of_id is null
        and s.is_active
      order by e.published_at desc nulls last, e.discovered_at desc, e.id desc
      limit 8
    `;
    return { status: "ready", data: rows.map(mapEvidence) };
  } catch {
    return failed();
  }
}
