import assert from "node:assert/strict";
import test from "node:test";

import { parseCompetitionScopeKey, selectPlayerContext } from "./player-context";

test("parses explicit competition player scopes", () => {
  assert.deepEqual(parseCompetitionScopeKey("competition:ENG_PL:2017/18"), {
    competitionCode: "ENG_PL",
    seasonLabel: "2017/18",
  });
  assert.equal(parseCompetitionScopeKey("core:2017/18"), null);
  assert.equal(parseCompetitionScopeKey("competition:ENG_PL"), null);
});

test("selects requested player context exactly", () => {
  const contexts = [
    { scopeKey: "competition:ENG_PL:2025/26" },
    { scopeKey: "competition:ENG_PL:2017/18" },
  ];
  assert.equal(
    selectPlayerContext(contexts, "competition:ENG_PL:2017/18")?.scopeKey,
    "competition:ENG_PL:2017/18",
  );
  assert.equal(selectPlayerContext(contexts, "competition:ENG_PL:2016/17"), null);
});

test("defaults only when no player context was requested", () => {
  const contexts = [{ scopeKey: "competition:ENG_PL:2017/18" }];
  assert.equal(selectPlayerContext(contexts, "")?.scopeKey, "competition:ENG_PL:2017/18");
  assert.equal(selectPlayerContext([], ""), null);
});
