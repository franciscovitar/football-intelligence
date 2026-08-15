"use server";

import { revalidatePath } from "next/cache";

import { isWriteAuthorized } from "@/lib/auth/write-session";

import { performAddWatchlistEntry, performRemoveWatchlistEntry } from "./mutations";

export async function addWatchlistEntry(formData: FormData) {
  const changed = await performAddWatchlistEntry(await isWriteAuthorized(), formData);
  if (changed) { revalidatePath("/watchlist"); revalidatePath("/"); }
}

export async function removeWatchlistEntry(formData: FormData) {
  const changed = await performRemoveWatchlistEntry(await isWriteAuthorized(), formData);
  if (changed) { revalidatePath("/watchlist"); revalidatePath("/"); }
}
