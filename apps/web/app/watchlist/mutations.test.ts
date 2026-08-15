import assert from "node:assert/strict";
import { test } from "node:test";

import type { getDatabase } from "../../lib/db/postgres.ts";
import { performAddWatchlistEntry, performRemoveWatchlistEntry } from "./mutations.ts";

type Sql = ReturnType<typeof getDatabase>;

function throwingDb(): Sql {
  throw new Error("must not touch the database when unauthorized");
}

function fakeDb(existsResult: boolean) {
  const calls: string[] = [];
  const sql = ((strings: TemplateStringsArray) => {
    const text = strings.join("?");
    calls.push(text);
    if (text.includes("select exists")) return Promise.resolve([{ exists: existsResult }]);
    return Promise.resolve([]);
  }) as unknown as Sql;
  return { sql, calls, getDb: () => sql };
}

function addForm(playerId: unknown, category = "manual", reason = ""): FormData {
  const formData = new FormData();
  formData.set("playerId", String(playerId));
  formData.set("category", category);
  formData.set("reason", reason);
  return formData;
}

function removeForm(playerId: unknown): FormData {
  const formData = new FormData();
  formData.set("playerId", String(playerId));
  return formData;
}

test("performAddWatchlistEntry never touches the database when unauthorized", async () => {
  const changed = await performAddWatchlistEntry(false, addForm(1), throwingDb);
  assert.equal(changed, false);
});

test("performRemoveWatchlistEntry never touches the database when unauthorized", async () => {
  const changed = await performRemoveWatchlistEntry(false, removeForm(1), throwingDb);
  assert.equal(changed, false);
});

test("performAddWatchlistEntry inserts when authorized and the player is real V2", async () => {
  const { getDb, calls } = fakeDb(true);
  const changed = await performAddWatchlistEntry(true, addForm(42, "emerging", "worth a look"), getDb);
  assert.equal(changed, true);
  assert.ok(calls.some((text) => text.includes("select exists")));
  assert.ok(calls.some((text) => text.includes("insert into analytics.player_watchlist_entries")));
});

test("performRemoveWatchlistEntry deletes when authorized", async () => {
  const { getDb, calls } = fakeDb(true);
  const changed = await performRemoveWatchlistEntry(true, removeForm(42), getDb);
  assert.equal(changed, true);
  assert.ok(calls.some((text) => text.includes("delete from analytics.player_watchlist_entries")));
});

test("performAddWatchlistEntry rejects a non-real player even when authorized", async () => {
  const { getDb, calls } = fakeDb(false);
  const changed = await performAddWatchlistEntry(true, addForm(42), getDb);
  assert.equal(changed, false);
  assert.ok(!calls.some((text) => text.includes("insert into analytics.player_watchlist_entries")));
});

test("performAddWatchlistEntry rejects invalid input without ever inserting", async () => {
  const { getDb, calls } = fakeDb(true);
  const changed = await performAddWatchlistEntry(true, addForm(-1), getDb);
  assert.equal(changed, false);
  assert.ok(!calls.some((text) => text.includes("insert into analytics.player_watchlist_entries")));
});

test("performRemoveWatchlistEntry rejects invalid input without ever deleting", async () => {
  const { getDb, calls } = fakeDb(true);
  const changed = await performRemoveWatchlistEntry(true, removeForm("not-a-number"), getDb);
  assert.equal(changed, false);
  assert.ok(!calls.some((text) => text.includes("delete from analytics.player_watchlist_entries")));
});
