// First screen: editorial hero + choose a data source (demo dataset or upload).

import { useRef, useState } from "react";
import { loadDemo, uploadCsv, type Health } from "../api";
import type { Session } from "../types";

// "Claude call #1/#2" is only accurate on the paid backend; on a local run the
// calls go to Ollama. Build the feature copy from the active engine's noun.
function features(callNoun: string) {
  return [
    { title: "Auto-clean", text: "Fixes dates, currency text, duplicates and encodings — with an auditable report of every change." },
    { title: "Proactive insights", text: `Finds 3–5 patterns unprompted, no question needed (${callNoun} #1).` },
    { title: "Self-critique", text: `A second, independent model reviews each finding for statistical validity (${callNoun} #2).` },
    { title: "Ask anything", text: "Plain-English follow-ups with session memory and auto-generated charts." },
  ];
}

export default function Landing({ onReady, health }: { onReady: (s: Session) => void; health: Health | null }) {
  const [loading, setLoading] = useState<"demo" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const badgeLabel = health?.label ?? "Powered by Claude";
  const isLocal = health?.is_local ?? false;
  const FEATURES = features(health?.call_noun ?? "Claude call");

  async function run(kind: "demo" | "upload", file?: File) {
    setError(null);
    setLoading(kind);
    try {
      const session = kind === "demo" ? await loadDemo() : await uploadCsv(file!);
      onReady(session);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load the dataset.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-20 sm:py-28">
      {/* Masthead rule + eyebrow */}
      <div className="flex items-center justify-between border-b border-line pb-3">
        <span className="kicker">Autonomous Data Analyst</span>
        <span title={health?.engine_label} className="inline-flex items-center gap-2 text-[11px] text-ink-faint">
          <span className={`h-1.5 w-1.5 rounded-full ${isLocal ? "bg-approve" : "bg-accent"}`} />
          {badgeLabel}
        </span>
      </div>

      {/* Hero */}
      <div className="animate-fade-up pt-12">
        <span className="mb-6 block h-[3px] w-16 bg-accent" />
        <h1 className="max-w-3xl font-serif text-5xl font-medium leading-[1.05] tracking-tight text-ink sm:text-7xl">
          A <span className="italic text-accent">junior analyst</span> for your messiest spreadsheets.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-soft">
          Drop in a CSV. It cleans the data, proactively surfaces patterns, critiques its own
          findings for statistical validity, and answers your questions with charts.
        </p>

        <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            onClick={() => run("demo")}
            disabled={loading !== null}
            className="rounded-md bg-ink px-6 py-3 text-sm font-semibold text-paper transition hover:bg-black disabled:opacity-50"
          >
            {loading === "demo" ? "Loading…" : "Try the Superstore demo"}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={loading !== null}
            className="rounded-md border border-ink/25 px-6 py-3 text-sm font-semibold text-ink transition hover:border-ink hover:bg-ink/[0.03] disabled:opacity-50"
          >
            {loading === "upload" ? "Uploading…" : "Upload a CSV (≤ 5 MB)"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) run("upload", f);
              e.target.value = "";
            }}
          />
        </div>

        {health && !health.ready && (
          <div className="mt-6 max-w-xl border-l-2 border-downgrade bg-downgrade/[0.06] px-4 py-3 text-sm text-ink-soft">
            <span className="font-semibold text-ink">Claude backend selected but no API key is set.</span>{" "}
            Set <code className="rounded bg-ink/[0.06] px-1">ANTHROPIC_API_KEY</code>, or run for free with{" "}
            <code className="rounded bg-ink/[0.06] px-1">LLM_PROVIDER=ollama</code>.
          </div>
        )}

        {error && (
          <div className="mt-6 max-w-xl border-l-2 border-accent bg-accent-soft px-4 py-3 text-sm text-accent-ink">
            {error}
          </div>
        )}
      </div>

      {/* Feature ledger — numbered, hairline-separated, editorial */}
      <div className="mt-20 border-t border-line">
        {FEATURES.map((f, i) => (
          <div
            key={f.title}
            className="animate-fade-up grid grid-cols-[auto_1fr] items-baseline gap-x-6 gap-y-1 border-b border-line py-6 sm:grid-cols-[3rem_14rem_1fr]"
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <span className="font-serif text-lg text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
            <h3 className="text-base font-semibold text-ink">{f.title}</h3>
            <p className="col-span-2 text-sm leading-relaxed text-ink-soft sm:col-span-1">{f.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
