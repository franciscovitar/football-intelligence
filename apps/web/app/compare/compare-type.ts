/**
 * Compare's `?type=` default resolution, factored out so it is unit-
 * testable without pulling in the rest of `page.tsx`'s `@/*`-aliased
 * imports (only Next.js's bundler resolves that alias; a plain `node
 * --test` run does not -- see `compare-type.test.ts`).
 *
 * Player V2 evidence is now published across the historical core-league
 * contexts, so the generic `/compare` entry point should open the player
 * comparison. `?type=team` remains fully supported for explicit team use.
 */

export type CompareType = "team" | "player";

export function resolveCompareType(rawType: string): CompareType {
  return rawType === "team" ? "team" : "player";
}
