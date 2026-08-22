import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveCompareType } from "./compare-type.ts";

test("no type param defaults to team", () => {
  assert.equal(resolveCompareType(""), "team");
});

test("?type=team stays team", () => {
  assert.equal(resolveCompareType("team"), "team");
});

test("?type=player is honored", () => {
  assert.equal(resolveCompareType("player"), "player");
});

test("an unrecognized type value falls back to team, not player", () => {
  assert.equal(resolveCompareType("something-else"), "team");
});
