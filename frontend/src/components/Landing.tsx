// First screen: hero + choose a data source (demo dataset or upload a CSV).

import { useRef, useState } from "react";
import { loadDemo, uploadCsv, type Health } from "../api";
import type { Session } from "../types";

// "Claude call #1/#2" is only accurate on the paid backend; on a local run the
// calls go to Ollama. Build the feature copy from the active engine's noun.
function features(callNoun: string) {
  return [
    { icon: "🧹", title: "Auto-clean", text: "Fixes dates, currency text, duplicates & encodings with an auditable report." },
    { icon: "🔍", title: "Proactive insights", text: `Finds 3–5 patterns unprompted — no question needed (${callNoun} #1).` },
    { icon: "🧠", title: "Self-critique", text: `A second, independent AI reviews each finding for validity (${callNoun} #2).` },
    { icon: "📈", title: "Ask anything", text: "Plain-English Q&A with memory and auto-generated charts." },
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
    <div className="mx-auto max-w-4xl px-6 py-16 text-center">
      <div className="animate-fade-up">
        <span
          title={health?.engine_label}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${isLocal ? "bg-emerald-400" : "bg-indigo-400"}`} />
          {badgeLabel} · two-agent pipeline
        </span>
        <h1 className="mt-6 bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-4xl font-extrabold tracking-tight text-transparent sm:text-5xl">
          Autonomous Data Analyst
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-slate-400">
          Drop in a messy CSV and get a junior analyst that cleans it, proactively finds insights,
          critiques its own findings for statistical validity, and answers your questions with charts.
        </p>
      </div>

      {health && !health.ready && (
        <div className="mx-auto mt-6 max-w-lg rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <span className="font-semibold">Claude backend selected but no API key is set.</span> Set{" "}
          <code className="rounded bg-black/30 px-1">ANTHROPIC_API_KEY</code>, or run for free with{" "}
          <code className="rounded bg-black/30 px-1">LLM_PROVIDER=ollama</code>. You can still load a
          dataset and see the cleaning report — only the AI steps need the backend.
        </div>
      )}

      <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <button
          onClick={() => run("demo")}
          disabled={loading !== null}
          className="w-full rounded-xl bg-indigo-500 px-6 py-3 font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:bg-indigo-400 disabled:opacity-50 sm:w-auto"
        >
          {loading === "demo" ? "Loading…" : "Try the Superstore demo"}
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={loading !== null}
          className="w-full rounded-xl border border-white/15 bg-white/5 px-6 py-3 font-semibold text-slate-200 transition hover:border-white/25 disabled:opacity-50 sm:w-auto"
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

      {error && (
        <div className="mx-auto mt-5 max-w-md rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="mt-14 grid grid-cols-1 gap-4 text-left sm:grid-cols-2">
        {FEATURES.map((f, i) => (
          <div key={f.title} className="card animate-fade-up p-5" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="text-2xl">{f.icon}</div>
            <h3 className="mt-2 font-semibold text-slate-100">{f.title}</h3>
            <p className="mt-1 text-sm text-slate-400">{f.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
