"use server";

import { revalidatePath } from "next/cache";

import { getDatabase } from "@/lib/db/postgres";

const CATEGORIES = new Set(["manual", "emerging", "regression_watch", "underperforming_process"]);

export async function addWatchlistEntry(formData: FormData) {
  const sql = getDatabase(); if (!sql) return;
  const playerId = Number(formData.get("playerId")); const category = String(formData.get("category") ?? "manual"); const reason = String(formData.get("reason") ?? "").trim().slice(0, 500);
  if (!Number.isInteger(playerId) || playerId < 1 || !CATEGORIES.has(category)) return;
  const real = await sql<Array<{ exists: boolean }>>`select exists (select 1 from analytics.product_player_detail_v2 where player_id = ${playerId}) as exists`;
  if (!real[0]?.exists) return;
  await sql`insert into analytics.player_watchlist_entries (player_id, category, reason) values (${playerId}, ${category}, ${reason || null}) on conflict (player_id) do update set category = excluded.category, reason = excluded.reason`;
  revalidatePath("/watchlist"); revalidatePath("/");
}

export async function removeWatchlistEntry(formData: FormData) {
  const sql = getDatabase(); if (!sql) return; const playerId = Number(formData.get("playerId")); if (!Number.isInteger(playerId) || playerId < 1) return;
  await sql`delete from analytics.player_watchlist_entries where player_id = ${playerId}`; revalidatePath("/watchlist"); revalidatePath("/");
}
