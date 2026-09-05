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
  RepriceResult,
  Reproducibility,
  SafetyReport,
  ScenarioDetail,
  ScenarioIndex,
} from "@/types/domain";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number | null;
  /**
   * The engine's structured `detail`, when it sent one.
   *
   * A refused request is a finding, not a transport failure: `/reprice` answers
   * 422 with the rule that fired and the numbers it fired on. Flattening that
   * to a message string would leave the view unable to say which limit was
   * breached, so the object is carried through untouched.
   */
  readonly detail: unknown;

  constructor(message: string, status: number | null, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
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
    let message = `${response.status} ${response.statusText}`;
    let detail: unknown = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body?.detail) {
        detail = body.detail;
        // A string detail is already the message. A structured one carries its
        // own wording under `reason`, and the object is kept either way.
        if (typeof detail === "string") message = detail;
        else if (
          typeof detail === "object" &&
          detail !== null &&
          "refusal" in detail
        ) {
          const refusal = (detail as { refusal?: { reason?: string } }).refusal;
          if (refusal?.reason) message = refusal.reason;
        }
      }
    } catch {
      /* the body was not JSON; the status line is what we have */
    }
    throw new ApiError(message, response.status, detail);
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

/**
 * Ask the engine what one merchant's offer is worth at a given incentive.
 *
 * `incentive` is the amount the merchant has *committed* to, not what they are
 * typing: the caller holds the draft and moves this value on submit, so the
 * request is made when an evaluation is asked for rather than on every
 * keystroke. Passing `null` makes no request at all, which is how the
 * read-only merchants render.
 *
 * A refused request arrives as an `ApiError` carrying the engine's `refusal`
 * object on `.detail`. Nothing is computed here; the response is rendered.
 */
export const useReprice = (id: string | null, incentive: number | null) =>
  useApi<RepriceResult>(
    id !== null && incentive !== null
      ? `/api/scenarios/${id}/reprice?incentive_inr=${encodeURIComponent(incentive)}`
      : null,
  );
