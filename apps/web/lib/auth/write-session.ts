import { cookies } from "next/headers";

import {
  createWriteSessionValue,
  verifyWriteSessionValue,
  WRITE_SESSION_COOKIE,
  WRITE_SESSION_TTL_MS,
} from "@/lib/auth/write-guard";

export { isWriteAuthConfigured, verifyWriteToken } from "@/lib/auth/write-guard";

export async function isWriteAuthorized(): Promise<boolean> {
  const store = await cookies();
  return verifyWriteSessionValue(store.get(WRITE_SESSION_COOKIE)?.value);
}

/** Returns false when no write secret is configured (nothing to establish). */
export async function establishWriteSession(): Promise<boolean> {
  const value = createWriteSessionValue();
  if (!value) return false;
  const store = await cookies();
  store.set(WRITE_SESSION_COOKIE, value, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: Math.floor(WRITE_SESSION_TTL_MS / 1000),
  });
  return true;
}

export async function clearWriteSession(): Promise<void> {
  const store = await cookies();
  store.delete(WRITE_SESSION_COOKIE);
}
