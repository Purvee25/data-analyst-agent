// One AI insight: the finding, its category, the critic's verdict + confidence,
// the supporting numbers, and the critic's reasoning. This is the visual payoff
// of the two-agent pipeline — the critic's judgement is shown, not hidden.

import { useState } from "react";
import { emailInsight } from "../api";
import type { Category, Insight, Verdict } from "../types";

const CATEGORY_STYLE: Record<Category, string> = {
  trend: "text-ink-soft",
  anomaly: "text-accent",
  comparison: "text-ink-soft",
  correlation: "text-ink-soft",
};

const VERDICT_STYLE: Record<Verdict, { label: string; cls: string }> = {
  approve: { label: "Approved", cls: "text-approve" },
  downgrade: { label: "Downgraded", cls: "text-downgrade" },
};

function confColor(c: number): string {
  if (c >= 0.7) return "bg-approve";
  if (c >= 0.4) return "bg-downgrade";
  return "bg-accent";
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
      className="card card-lift animate-fade-up p-6"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className={`kicker ${CATEGORY_STYLE[insight.category]}`}>{insight.category}</span>
        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${verdict.cls}`}>
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {verdict.label}
        </span>
      </div>

      <p className="font-serif text-lg font-medium leading-snug text-ink">{insight.insight}</p>

      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        <span className="font-semibold text-ink">Supporting data — </span>
        {insight.supporting_data}
      </p>

      {/* Confidence meter */}
      <div className="mt-5">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="kicker">Confidence</span>
          <span className="text-sm font-semibold tabular-nums text-ink">{pct}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink/[0.06]">
          <div
            className={`h-full rounded-full ${confColor(insight.confidence)} transition-all duration-700`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Critic reasoning */}
      <div className="mt-5 border-l-2 border-line-strong pl-3">
        <p className="text-sm leading-relaxed text-ink-soft">
          <span className="font-semibold text-ink">Critic&apos;s review — </span>
          {insight.critic_reasoning}
        </p>
      </div>

      {/* Real-world action (USP #4): human-confirmed email via the local MCP server. */}
      <div className="mt-5 border-t border-line pt-4">
        {email.kind === "sent" ? (
          <p className="text-xs font-medium text-approve">✓ {email.message}</p>
        ) : email.kind === "confirming" ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-ink-soft">Send this insight as an email alert?</span>
            <button
              onClick={confirmSend}
              className="rounded-md bg-ink px-3 py-1.5 text-xs font-semibold text-paper transition hover:bg-black"
            >
              Confirm send
            </button>
            <button
              onClick={() => setEmail({ kind: "idle" })}
              className="rounded-md border border-ink/20 px-3 py-1.5 text-xs text-ink transition hover:border-ink"
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
              className="rounded-md border border-ink/20 px-3 py-1.5 text-xs font-medium text-ink transition hover:border-ink hover:bg-ink/[0.03] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {email.kind === "sending" ? "Sending…" : "Email this insight"}
            </button>
            {!emailConfigured && <span className="text-xs text-ink-faint">Set SMTP env vars to enable</span>}
            {email.kind === "error" && <span className="text-xs text-accent">{email.message}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
