// Thin fetch wrapper around the FastAPI backend.
//
// Every call routes through `request`, which turns a non-2xx response into a
// thrown Error carrying the backend's clean `detail` message. The UI catches
// that and shows it — so a failed API key / rate limit / bad upload surfaces as
// a friendly banner, never a crash. This mirrors the backend's own contract of
// always returning {"detail": "..."} instead of a traceback.

import type { Insight, Metrics, QAResult, Session } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, options);
  } catch {
    throw new Error("Could not reach the analyst server. Is the backend running on port 8010?");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function loadDemo(): Promise<Session> {
  return request<Session>("/api/session/demo", { method: "POST" });
}

export function uploadCsv(file: File): Promise<Session> {
  const form = new FormData();
  form.append("file", file);
  return request<Session>("/api/session/upload", { method: "POST", body: form });
}

export function generateInsights(sessionId: string): Promise<{ insights: Insight[]; requests_used: number }> {
  return request("/api/insights", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function askQuestion(sessionId: string, question: string): Promise<QAResult> {
  return request<QAResult>("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
}

export interface Health {
  status: string;
  api_key_configured: boolean;
  ready: boolean;
  provider: string;
  model: string;
  is_local: boolean;
  is_free: boolean; // true for any no-cost backend (local Ollama or free Groq)
  label: string; // e.g. "Powered by Claude" | "Running free on a local model"
  engine_label: string; // e.g. "qwen2.5-coder:7b · local & free"
  call_noun: string; // e.g. "Claude call" | "local model call"
  email_configured: boolean; // whether SMTP env is set server-side
}

export function health(): Promise<Health> {
  return request("/api/health");
}

export function getMetrics(): Promise<Metrics> {
  return request("/api/metrics");
}

export function emailInsight(
  sessionId: string,
  insight: Insight,
): Promise<{ result: string; actions_used: number; actions_max: number }> {
  return request("/api/action/email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, insight }),
  });
}
