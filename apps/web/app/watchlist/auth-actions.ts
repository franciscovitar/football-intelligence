"use server";

import { revalidatePath } from "next/cache";

import { verifyWriteToken } from "@/lib/auth/write-guard";
import { clearWriteSession, establishWriteSession } from "@/lib/auth/write-session";

export async function authorizeWrites(formData: FormData) {
  const token = String(formData.get("token") ?? "");
  if (!verifyWriteToken(token)) return;
  if (await establishWriteSession()) revalidatePath("/watchlist");
}

export async function deauthorizeWrites() {
  await clearWriteSession();
  revalidatePath("/watchlist");
}
