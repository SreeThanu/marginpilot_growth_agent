/**
 * Which merchant the whole application is looking at.
 *
 * The URL is the state, not a copy of it. `?s=A` is read through
 * `useSyncExternalStore`, so a deep link, the back button and the comparator in
 * the chrome all move the app the same way, and every screen stays on the same
 * merchant as you navigate between them.
 */

"use client";

import { useCallback, useSyncExternalStore } from "react";

const VALID = ["A", "B", "C"] as const;
export type ScenarioId = (typeof VALID)[number];

/**
 * A is the landing state, and the choice is deliberate.
 *
 * It is the merchant where the assistant asked to promote and the policy said
 * no — the one moment that shows what this product is for. C ends the story;
 * it is a poor place to begin it, because there the model and the policy agree
 * and the machinery has nothing visible to do.
 */
const DEFAULT_SCENARIO: ScenarioId = "A";

/** Fired after a programmatic URL change, which emits no popstate of its own. */
const CHANGED = "marginpilot:scenario";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

function readScenario(): ScenarioId {
  const raw = new URLSearchParams(window.location.search).get("s");
  if (!raw) return DEFAULT_SCENARIO;
  const upper = raw.toUpperCase() as ScenarioId;
  return VALID.includes(upper) ? upper : DEFAULT_SCENARIO;
}

/** The server has no query string, so it renders the default and hydrates over it. */
function serverScenario(): ScenarioId {
  return DEFAULT_SCENARIO;
}

export interface ScenarioState {
  scenario: ScenarioId;
  setScenario: (next: ScenarioId) => void;
}

export function useScenarioId(): ScenarioState {
  const scenario = useSyncExternalStore(
    subscribe,
    readScenario,
    serverScenario,
  );

  const setScenario = useCallback((next: ScenarioId) => {
    const url = new URL(window.location.href);
    url.searchParams.set("s", next);
    window.history.replaceState(null, "", url);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return { scenario, setScenario };
}

export const SCENARIO_IDS: readonly ScenarioId[] = VALID;

/** Build an in-app href that keeps the current merchant selected. */
export function withScenario(path: string, scenario: ScenarioId): string {
  return `${path}?s=${scenario}`;
}
