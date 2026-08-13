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
      <header className="sticky top-0 z-10 border-b border-line bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-ink font-serif text-base font-medium text-paper">
              A
            </span>
            <div className="flex items-baseline gap-3">
              <p className="font-serif text-lg font-medium text-ink">Autonomous Data Analyst</p>
              <p className="hidden text-xs text-ink-faint sm:block">{session.filename}</p>
            </div>
          </div>
          <div className="flex items-center gap-5">
            <p className="text-sm tabular-nums text-ink-soft">
              <span className="font-semibold text-ink">{used}</span>
              <span className="text-ink-faint"> / {max}</span>
            </p>
            <button
              onClick={() => {
                setSession(null);
                setUsed(0);
              }}
              className="rounded-md border border-ink/20 px-3 py-1.5 text-xs font-medium text-ink transition hover:border-ink hover:bg-ink/[0.03]"
            >
              New dataset
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-10 px-6 py-10">
        <div className="animate-fade-up border-b border-line pb-6">
          <p className="kicker accent-mark mb-2">Dataset · cleaned &amp; ready</p>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-ink">
            {session.rows.toLocaleString()} <span className="text-ink-faint">rows</span> ×{" "}
            {session.cols} <span className="text-ink-faint">columns</span>
          </h1>
        </div>

        <DataQuality report={session.quality} />

        <Section title="Preview — first 20 rows">
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

        <Section title="Agent metrics">
          <MetricsPanel refreshKey={metricsKey} />
        </Section>

        <footer className="border-t border-line pt-6 text-center text-xs text-ink-faint">
          Validated · rate-limited · logged{health?.is_free ? ` · ${health.engine_label}` : ""}
        </footer>
      </main>
    </div>
  );
}
