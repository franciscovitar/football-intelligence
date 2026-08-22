/**
 * Compare's `?type=` default resolution, factored out so it is unit-
 * testable without pulling in the rest of `page.tsx`'s `@/*`-aliased
 * imports (only Next.js's bundler resolves that alias; a plain `node
 * --test` run does not -- see `compare-type.test.ts`).
 *
 * V1 Closure Pass 1: team evidence is real and reachable today; player
 * evidence is not. No explicit `?type=` should default to the team
 * comparison, never the empty player one. `?type=player` remains fully
 * supported for anyone who deliberately asks for it.
 */

export type CompareType = "team" | "player";

export function resolveCompareType(rawType: string): CompareType {
  return rawType === "player" ? "player" : "team";
}
