// Top-level orchestrator: shows the Landing screen until a dataset is loaded,
// then the dashboard (data quality, preview, insights, Q&A). Holds the single
// piece of shared state — the active Session — and the rate-limit counter.

import { useEffect, useState } from "react";
import Landing from "./components/Landing";
import DataQuality from "./components/DataQuality";
import PreviewTable from "./components/PreviewTable";
import InsightsPanel from "./components/InsightsPanel";
import QAPanel from "./components/QAPanel";
import MetricsPanel from "./components/MetricsPanel";
import Section from "./components/Section";
import { health as fetchHealth, type Health } from "./api";
import type { Session } from "./types";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [used, setUsed] = useState(0);
  // Bumped whenever new rows are logged (an insight run or a Q&A turn) so the
  // metrics panel refetches. Keeps observability live without polling.
  const [metricsKey, setMetricsKey] = useState(0);
  const bumpMetrics = () => setMetricsKey((k) => k + 1);
  // The active LLM backend (Claude vs a free local model). Fetched once so every
  // "Powered by …" label reflects what's really running, not a hardcoded claim.
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null)); // badge just falls back to neutral copy
  }, []);

  if (!session) {
    return (
      <div className="app-bg min-h-full">
        <Landing
          health={health}
          onReady={(s) => {
            setSession(s);
            setUsed(s.requests_used);
          }}
        />
      </div>
    );
  }

  const max = session.requests_max;

  return (
    <div className="app-bg min-h-full">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-white/5 bg-slate-950/60 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-bold">
              📊
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-slate-100">Autonomous Data Analyst</p>
              <p className="text-xs text-slate-500">{session.filename}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {health && (
              <span
                title={health.engine_label}
                className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs sm:inline-flex ${
                  health.is_local
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : "border-indigo-500/30 bg-indigo-500/10 text-indigo-300"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${health.is_local ? "bg-emerald-400" : "bg-indigo-400"}`} />
                {health.is_local ? "Local · free" : "Claude"}
              </span>
            )}
            <div className="text-right">
              <p className="text-xs text-slate-500">AI requests</p>
              <p className="text-sm font-semibold text-slate-200">
                {used} <span className="text-slate-500">/ {max}</span>
              </p>
            </div>
            <button
              onClick={() => {
                setSession(null);
                setUsed(0);
              }}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:border-white/20"
            >
              New dataset
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        <div className="animate-fade-up">
          <h1 className="text-2xl font-bold text-slate-50">
            {session.rows.toLocaleString()} rows × {session.cols} columns
            <span className="ml-2 text-base font-normal text-slate-500">cleaned & ready</span>
          </h1>
        </div>

        <DataQuality report={session.quality} />

        <Section title="👀 Preview (first 20 rows)">
          <PreviewTable preview={session.preview} />
        </Section>

        <InsightsPanel
          sessionId={session.session_id}
          onRequestUsed={setUsed}
          onComplete={bumpMetrics}
          emailConfigured={health?.email_configured ?? false}
        />

        <QAPanel
          sessionId={session.session_id}
          onRequestUsed={(n) => {
            setUsed(n);
            bumpMetrics();
          }}
        />

        <Section title="📈 Agent metrics">
          <MetricsPanel refreshKey={metricsKey} />
        </Section>

        <footer className="pt-4 text-center text-xs text-slate-600">
          Cleaning runs locally · insights use two independent {health ? `${health.call_noun}s` : "model calls"}
          {health?.is_local ? ` (${health.engine_label})` : ""} · every request is validated, rate-limited & logged.
        </footer>
      </main>
    </div>
  );
}
