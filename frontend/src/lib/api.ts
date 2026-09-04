/**
 * The only place this application talks to MarginPilot.
 *
 * Every response is passed through untouched. There is no client-side
 * normalisation step, no "fill in the missing field" and no fallback object:
 * if the adapter cannot answer, the hook returns an error and the screen says
 * so. A view that silently substituted a plausible number for a failed request
 * would be indistinguishable, on camera, from a view showing a real one.
 */

"use client";

import {
  useCallback,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";

import type {
  AuditTrail,
  Reproducibility,
  SafetyReport,
  ScenarioDetail,
  ScenarioIndex,
} from "@/types/domain";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      signal,
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError(
      "The MarginPilot engine is not reachable. Start it with `python -m api`.",
      null,
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* the body was not JSON; the status line is what we have */
    }
    throw new ApiError(detail, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "The engine returned a response this client could not read as JSON.",
      response.status,
    );
  }
}

export interface Query<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  retry: () => void;
}

/** What a completed request left behind, tagged with the request it answered. */
interface Settled<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/* -------------------------------------------------------------------------- */
/* Recovery                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Retry is global, because the failure usually is.
 *
 * When the engine is not running, every request on the screen fails — the
 * decision, and the merchant switch in the chrome that names it. Retrying only
 * the one the user happened to click leaves the rest showing a stale dash next
 * to live figures, which is worse than either state on its own.
 */
let attempt = 0;
const waiting = new Set<() => void>();

function subscribeAttempt(onChange: () => void): () => void {
  waiting.add(onChange);
  return () => {
    waiting.delete(onChange);
  };
}

const readAttempt = () => attempt;
const serverAttempt = () => 0;

export function retryAll(): void {
  attempt += 1;
  waiting.forEach((notify) => notify());
}

/**
 * Fetch one path, with explicit loading, error and retry states.
 *
 * State is written only from the request's own callbacks and is tagged with the
 * key it answered, so "loading" is derived from the tag rather than toggled on
 * the way in. Switching merchants therefore never shows the previous merchant's
 * figures under the new merchant's name.
 */
export function useApi<T>(path: string | null): Query<T> {
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const nonce = useSyncExternalStore(
    subscribeAttempt,
    readAttempt,
    serverAttempt,
  );

  const retry = useCallback(() => retryAll(), []);
  const key = path === null ? null : `${path}#${nonce}`;

  useEffect(() => {
    if (path === null || key === null) return;
    const controller = new AbortController();

    get<T>(path, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setSettled({ key, data: payload, error: null });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setSettled({
          key,
          data: null,
          error:
            cause instanceof ApiError
              ? cause
              : new ApiError("Unexpected client error.", null),
        });
      });

    return () => controller.abort();
  }, [path, key]);

  const fresh = key !== null && settled?.key === key ? settled : null;

  return {
    data: fresh?.data ?? null,
    error: fresh?.error ?? null,
    loading: key !== null && fresh === null,
    retry,
  };
}

export const useScenarioIndex = () => useApi<ScenarioIndex>("/api/scenarios");

export const useScenario = (id: string | null) =>
  useApi<ScenarioDetail>(id ? `/api/scenarios/${id}` : null);

export const useAudit = (id: string | null) =>
  useApi<AuditTrail>(id ? `/api/scenarios/${id}/audit` : null);

export const useSafety = () => useApi<SafetyReport>("/api/safety");

export const useReproducibility = () =>
  useApi<Reproducibility>("/api/reproducibility");
