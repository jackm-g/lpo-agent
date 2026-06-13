import type { ApiResponse } from "./types";
import { DEMO_CONFIRM, DEMO_NEED_INFO, DEMO_SOLVE } from "./demoData";

// Base URL for the LPO backend. In dev, Vite proxies "/api" -> FastAPI (see
// vite.config.ts). Override at build time with VITE_API_BASE.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export interface SolveParams {
  question: string;
  context?: string;
  requireConfirmation: boolean;
  maxRetries?: number;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${resp.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await resp.json()) as T;
}

/** Formulate (and, if confirmation is off, solve) — the first call. */
export function solve(p: SolveParams): Promise<ApiResponse> {
  return postJson<ApiResponse>("/v1/solve", {
    question: p.question,
    context: p.context ?? "",
    require_human_confirmation: p.requireConfirmation,
    max_retries: p.maxRetries ?? 3,
  });
}

/** Approve/reject a pending model — the second call. */
export function confirm(traceId: string, approved: boolean): Promise<ApiResponse> {
  return postJson<ApiResponse>("/v1/confirm", {
    trace_id: traceId,
    approved,
  });
}

// --------------------------------------------------------------------------- //
// Demo mode — runs the whole UX with no backend or API key. Keyword-matches the
// question the same way the Python MockProvider does, so the flow is faithful.
// --------------------------------------------------------------------------- //
function looksLikeMaintenance(q: string): boolean {
  return /bradley|motor pool|svc|service|repair|flr|powerpack|mech/i.test(q);
}
function hasNumbers(q: string): boolean {
  return /\d/.test(q);
}

export const demoApi = {
  solve(p: SolveParams): Promise<ApiResponse> {
    return new Promise((resolve) =>
      setTimeout(() => {
        if (!looksLikeMaintenance(p.question) || !hasNumbers(p.question)) {
          resolve(DEMO_NEED_INFO);
        } else if (p.requireConfirmation) {
          resolve(DEMO_SOLVE);
        } else {
          resolve(DEMO_CONFIRM);
        }
      }, 550),
    );
  },
  confirm(_traceId: string, approved: boolean): Promise<ApiResponse> {
    return new Promise((resolve) =>
      setTimeout(
        () =>
          resolve(
            approved
              ? DEMO_CONFIRM
              : {
                  status: "need_info",
                  message: "Model rejected at the human confirmation gate.",
                  trace_id: "demo",
                },
          ),
        450,
      ),
    );
  },
};
