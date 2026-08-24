import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveCompareType } from "./compare-type.ts";

test("no type param defaults to player", () => {
  assert.equal(resolveCompareType(""), "player");
});

test("?type=team stays team", () => {
  assert.equal(resolveCompareType("team"), "team");
});

test("?type=player stays player", () => {
  assert.equal(resolveCompareType("player"), "player");
});

test("an unrecognized type value falls back to player", () => {
  assert.equal(resolveCompareType("something-else"), "player");
});
