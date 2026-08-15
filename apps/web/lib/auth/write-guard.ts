/**
 * Single-user write authorization for public mutation surfaces (currently
 * just the Watchlist Server Actions). Deliberately framework-free -- no
 * `next/headers`, no database -- so the authorization decision itself can
 * be unit-tested without a request context or a live Postgres connection.
 * `lib/auth/write-session.ts` binds this to `next/headers` cookies.
 *
 * The app is single-user but publicly deployed, so mutations must not be
 * reachable by an arbitrary visitor. A hidden form field, Referer check, or
 * client-side check is not real authorization -- any of those can be
 * replayed by anyone who can view the page source. This instead requires
 * knowledge of a server-only secret (`FOOTBALL_INTELLIGENCE_WRITE_TOKEN`),
 * exchanged once for a signed, expiring, HttpOnly session cookie so the
 * raw secret is never repeatedly transmitted or stored client-side.
 */

import { createHmac, timingSafeEqual } from "node:crypto";

export const WRITE_SESSION_COOKIE = "fi_write_session";
export const WRITE_SESSION_TTL_MS = 12 * 60 * 60 * 1000;

function configuredSecret(): string | null {
  const value = process.env.FOOTBALL_INTELLIGENCE_WRITE_TOKEN?.trim();
  return value ? value : null;
}

export function isWriteAuthConfigured(): boolean {
  return configuredSecret() !== null;
}

function timingSafeStringsEqual(a: string, b: string): boolean {
  const bufferA = Buffer.from(a);
  const bufferB = Buffer.from(b);
  if (bufferA.length !== bufferB.length) return false;
  return timingSafeEqual(bufferA, bufferB);
}

export function verifyWriteToken(token: string): boolean {
  const secret = configuredSecret();
  if (!secret || !token) return false;
  return timingSafeStringsEqual(token, secret);
}

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

/**
 * Returns the value to store in the session cookie, or null when no
 * secret is configured (callers must treat that as "cannot authorize").
 */
export function createWriteSessionValue(now: number = Date.now()): string | null {
  const secret = configuredSecret();
  if (!secret) return null;
  const expiresAt = now + WRITE_SESSION_TTL_MS;
  const payload = String(expiresAt);
  return `${payload}.${sign(payload, secret)}`;
}

export function verifyWriteSessionValue(
  value: string | undefined | null,
  now: number = Date.now(),
): boolean {
  const secret = configuredSecret();
  if (!secret || !value) return false;
  const separator = value.indexOf(".");
  if (separator < 1) return false;
  const payload = value.slice(0, separator);
  const signature = value.slice(separator + 1);
  if (!payload || !signature) return false;
  if (!timingSafeStringsEqual(signature, sign(payload, secret))) return false;
  const expiresAt = Number(payload);
  return Number.isFinite(expiresAt) && now < expiresAt;
}
