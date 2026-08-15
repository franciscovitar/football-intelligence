/**
 * Watchlist mutation logic, factored out of the `"use server"` actions so
 * the authorization gate can be unit-tested without a Next.js request
 * context. `authorized` is an explicit parameter (decided by the caller via
 * `lib/auth/write-session.ts`) rather than read internally, so a test can
 * assert the safety-critical property directly: passing `authorized: false`
 * must never touch the database. `getDb` is injectable for the same reason
 * -- tests use a fake in place of a live Postgres connection.
 *
 * Imports `getDatabase` by relative path (not the `@/*` alias) so this
 * module, and only this module among the watchlist files, can be loaded
 * directly by a plain `node --test` run with no bundler/alias resolution.
 */

import { getDatabase } from "../../lib/db/postgres.ts";

type DbGetter = typeof getDatabase;

const CATEGORIES = new Set(["manual", "emerging", "regression_watch", "underperforming_process"]);

export async function performAddWatchlistEntry(
  authorized: boolean,
  formData: FormData,
  getDb: DbGetter = getDatabase,
): Promise<boolean> {
  if (!authorized) return false;
  const sql = getDb();
  if (!sql) return false;

  const playerId = Number(formData.get("playerId"));
  const category = String(formData.get("category") ?? "manual");
  const reason = String(formData.get("reason") ?? "").trim().slice(0, 500);
  if (!Number.isInteger(playerId) || playerId < 1 || !CATEGORIES.has(category)) return false;

  const real = await sql<Array<{ exists: boolean }>>`select exists (select 1 from analytics.product_player_detail_v2 where player_id = ${playerId}) as exists`;
  if (!real[0]?.exists) return false;

  await sql`insert into analytics.player_watchlist_entries (player_id, category, reason) values (${playerId}, ${category}, ${reason || null}) on conflict (player_id) do update set category = excluded.category, reason = excluded.reason`;
  return true;
}

export async function performRemoveWatchlistEntry(
  authorized: boolean,
  formData: FormData,
  getDb: DbGetter = getDatabase,
): Promise<boolean> {
  if (!authorized) return false;
  const sql = getDb();
  if (!sql) return false;

  const playerId = Number(formData.get("playerId"));
  if (!Number.isInteger(playerId) || playerId < 1) return false;

  await sql`delete from analytics.player_watchlist_entries where player_id = ${playerId}`;
  return true;
}
