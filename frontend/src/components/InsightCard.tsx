// One AI insight: the finding, its category, the critic's verdict + confidence,
// the supporting numbers, and the critic's reasoning. This is the visual payoff
// of the two-agent pipeline — the critic's judgement is shown, not hidden.

import { useState } from "react";
import { emailInsight } from "../api";
import type { Category, Insight, Verdict } from "../types";

const CATEGORY_STYLE: Record<Category, string> = {
  trend: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  anomaly: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  comparison: "bg-violet-500/15 text-violet-300 ring-violet-500/30",
  correlation: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
};

const VERDICT_STYLE: Record<Verdict, { label: string; cls: string }> = {
  approve: { label: "✓ Approved", cls: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" },
  downgrade: { label: "▾ Downgraded", cls: "bg-amber-500/15 text-amber-300 ring-amber-500/30" },
};

function confColor(c: number): string {
  if (c >= 0.7) return "bg-emerald-400";
  if (c >= 0.4) return "bg-amber-400";
  return "bg-rose-400";
}

type EmailState =
  | { kind: "idle" }
  | { kind: "confirming" }
  | { kind: "sending" }
  | { kind: "sent"; message: string }
  | { kind: "error"; message: string };

export default function InsightCard({
  insight,
  index,
  sessionId,
  emailConfigured,
}: {
  insight: Insight;
  index: number;
  sessionId: string;
  emailConfigured: boolean;
}) {
  const verdict = VERDICT_STYLE[insight.critic_verdict] ?? VERDICT_STYLE.downgrade;
  const pct = Math.round(insight.confidence * 100);
  const [email, setEmail] = useState<EmailState>({ kind: "idle" });

  async function confirmSend() {
    setEmail({ kind: "sending" });
    try {
      const res = await emailInsight(sessionId, insight);
      setEmail({ kind: "sent", message: res.result });
    } catch (e) {
      setEmail({ kind: "error", message: e instanceof Error ? e.message : "Send failed." });
    }
  }

  return (
    <div
      className="card animate-fade-up p-5"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ring-1 ${CATEGORY_STYLE[insight.category]}`}
        >
          {insight.category}
        </span>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${verdict.cls}`}>
          {verdict.label}
        </span>
      </div>

      <p className="text-[15px] font-medium leading-relaxed text-slate-100">{insight.insight}</p>

      <p className="mt-2 text-sm text-slate-400">
        <span className="font-semibold text-slate-300">Supporting data: </span>
        {insight.supporting_data}
      </p>

      {/* Confidence meter */}
      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
          <span>Confidence</span>
          <span className="font-semibold text-slate-200">{pct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
          <div
            className={`h-full rounded-full ${confColor(insight.confidence)} transition-all duration-700`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Critic reasoning */}
      <div className="mt-4 rounded-lg border-l-2 border-slate-600 bg-white/[0.02] px-3 py-2">
        <p className="text-xs leading-relaxed text-slate-400">
          <span className="font-semibold text-slate-300">Critic&apos;s review: </span>
          {insight.critic_reasoning}
        </p>
      </div>

      {/* Real-world action (USP #4): human-confirmed email via the local MCP server. */}
      <div className="mt-4 border-t border-white/5 pt-3">
        {email.kind === "sent" ? (
          <p className="text-xs text-emerald-300">✓ {email.message}</p>
        ) : email.kind === "confirming" ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400">Send this insight as an email alert?</span>
            <button
              onClick={confirmSend}
              className="rounded-lg bg-emerald-500/90 px-3 py-1 text-xs font-semibold text-white transition hover:bg-emerald-400"
            >
              Confirm send
            </button>
            <button
              onClick={() => setEmail({ kind: "idle" })}
              className="rounded-lg border border-white/10 px-3 py-1 text-xs text-slate-300 transition hover:border-white/20"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setEmail({ kind: "confirming" })}
              disabled={!emailConfigured || email.kind === "sending"}
              title={emailConfigured ? undefined : "SMTP not configured on the server"}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 transition hover:border-white/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {email.kind === "sending" ? "Sending…" : "📧 Email this insight"}
            </button>
            {!emailConfigured && (
              <span className="text-xs text-slate-600">Set SMTP env vars to enable</span>
            )}
            {email.kind === "error" && <span className="text-xs text-rose-400">{email.message}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
