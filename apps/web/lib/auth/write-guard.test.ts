import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import {
  createWriteSessionValue,
  isWriteAuthConfigured,
  verifyWriteSessionValue,
  verifyWriteToken,
} from "./write-guard.ts";

const ENV_KEY = "FOOTBALL_INTELLIGENCE_WRITE_TOKEN";
let originalValue: string | undefined;

beforeEach(() => {
  originalValue = process.env[ENV_KEY];
});

afterEach(() => {
  if (originalValue === undefined) delete process.env[ENV_KEY];
  else process.env[ENV_KEY] = originalValue;
});

test("isWriteAuthConfigured is false when the secret is unset or blank", () => {
  delete process.env[ENV_KEY];
  assert.equal(isWriteAuthConfigured(), false);
  process.env[ENV_KEY] = "   ";
  assert.equal(isWriteAuthConfigured(), false);
});

test("isWriteAuthConfigured is true once a non-blank secret is set", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  assert.equal(isWriteAuthConfigured(), true);
});

test("verifyWriteToken rejects every token when unconfigured", () => {
  delete process.env[ENV_KEY];
  assert.equal(verifyWriteToken("anything"), false);
  assert.equal(verifyWriteToken(""), false);
});

test("verifyWriteToken accepts only the exact configured secret", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  assert.equal(verifyWriteToken("correct-horse-battery-staple"), true);
  assert.equal(verifyWriteToken("wrong-guess"), false);
  assert.equal(verifyWriteToken(""), false);
});

test("createWriteSessionValue returns null when unconfigured", () => {
  delete process.env[ENV_KEY];
  assert.equal(createWriteSessionValue(), null);
});

test("verifyWriteSessionValue rejects a missing or empty session", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  assert.equal(verifyWriteSessionValue(undefined), false);
  assert.equal(verifyWriteSessionValue(null), false);
  assert.equal(verifyWriteSessionValue(""), false);
});

test("verifyWriteSessionValue accepts a freshly signed, unexpired session", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  assert.equal(verifyWriteSessionValue(session, now + 1_000), true);
});

test("verifyWriteSessionValue rejects an expired session", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  // 13 hours later -- past the 12h TTL.
  assert.equal(verifyWriteSessionValue(session, now + 13 * 60 * 60 * 1000), false);
});

test("verifyWriteSessionValue rejects a tampered signature", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  const [payload] = session.split(".");
  const tampered = `${payload}.0000000000000000000000000000000000000000000000000000000000000000`;
  assert.equal(verifyWriteSessionValue(tampered, now + 1_000), false);
});

test("verifyWriteSessionValue rejects a tampered payload even with a matching-length forged signature", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  const [, signature] = session.split(".");
  const forgedExpiry = String(now + 1000 * 60 * 60 * 24 * 365);
  assert.equal(verifyWriteSessionValue(`${forgedExpiry}.${signature}`, now + 1_000), false);
});

test("verifyWriteSessionValue rejects a session signed under a different secret", () => {
  process.env[ENV_KEY] = "secret-a";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  process.env[ENV_KEY] = "secret-b";
  assert.equal(verifyWriteSessionValue(session, now + 1_000), false);
});

test("verifyWriteSessionValue rejects any session once unconfigured", () => {
  process.env[ENV_KEY] = "correct-horse-battery-staple";
  const now = 1_700_000_000_000;
  const session = createWriteSessionValue(now);
  assert.ok(session);
  delete process.env[ENV_KEY];
  assert.equal(verifyWriteSessionValue(session, now + 1_000), false);
});
