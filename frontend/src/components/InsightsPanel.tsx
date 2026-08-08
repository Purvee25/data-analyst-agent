// Streaming insights: opens an SSE connection to /api/insights/stream and
// reacts to each pipeline stage live. The agent-activity timeline advances in
// real time and vetted insight cards pop in one-by-one as the critic approves
// them — showcasing the two-agent architecture instead of hiding it.

import { useRef, useState } from "react";
import type { Insight } from "../types";
import InsightCard from "./InsightCard";
import AgentActivity, { type Stage } from "./AgentActivity";

export default function InsightsPanel({
  sessionId,
  onRequestUsed,
  onComplete,
  emailConfigured,
}: {
  sessionId: string;
  onRequestUsed: (n: number) => void;
  onComplete?: () => void;
  emailConfigured: boolean;
}) {
  const [stage, setStage] = useState<Stage>("idle");
  const [note, setNote] = useState<string>("");
  const [insights, setInsights] = useState<Insight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  // Guards against EventSource's built-in auto-reconnect re-running the whole
  // (billable/slow) pipeline once the stream closes: after a terminal event we
  // set this and ignore anything the reconnected socket delivers.
  const doneRef = useRef(false);

  const running = stage !== "idle" && stage !== "done" && stage !== "error";

  function start() {
    esRef.current?.close();
    doneRef.current = false;
    setInsights([]);
    setError(null);
    setRan(true);
    setStage("summarizing");
    setNote("");

    const es = new EventSource(`/api/insights/stream?session_id=${encodeURIComponent(sessionId)}`);
    esRef.current = es;

    es.onmessage = (e) => {
      if (doneRef.current) return;
      const evt = JSON.parse(e.data);
      switch (evt.stage) {
        case "summarizing":
        case "generating":
        case "critiquing":
          setStage(evt.stage);
          setNote(evt.message ?? "");
          break;
        case "generated":
          setNote(evt.message ?? "");
          break;
        case "insight":
          setInsights((prev) => [...prev, evt.insight as Insight]);
          break;
        case "done":
          doneRef.current = true;
          setStage("done");
          setNote(`${evt.approved} of ${evt.candidates} candidates approved by the critic.`);
          if (typeof evt.requests_used === "number") onRequestUsed(evt.requests_used);
          onComplete?.(); // a fresh run just logged rows — refresh the metrics panel
          es.close();
          break;
        case "error":
          doneRef.current = true;
          setStage("error");
          setError(evt.detail ?? "Insight generation failed.");
          es.close();
          break;
      }
    };

    es.onerror = () => {
      es.close();
      // If we already reached a terminal event, the close is expected — ignore.
      if (doneRef.current) return;
      doneRef.current = true;
      setStage("error");
      setError("Lost connection to the analyst server.");
    };
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-100">🔍 Proactive insights</h2>
        <button
          onClick={start}
          disabled={running}
          className="rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 disabled:opacity-50"
        >
          {running ? "Streaming…" : ran ? "Regenerate" : "Generate insights"}
        </button>
      </div>

      {(running || stage === "done" || stage === "error") && (
        <div className="mb-4">
          <AgentActivity stage={stage} note={note} />
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {insights.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {insights.map((ins, i) => (
            <InsightCard
              key={i}
              insight={ins}
              index={i}
              sessionId={sessionId}
              emailConfigured={emailConfigured}
            />
          ))}
        </div>
      )}

      {stage === "done" && insights.length === 0 && !error && (
        <p className="text-sm text-slate-400">
          Every candidate was rejected by the critic — nothing met the statistical bar this run.
        </p>
      )}

      {!ran && (
        <p className="text-sm text-slate-400">
          Click <span className="text-slate-200">Generate insights</span> and watch the two agents work
          live — the insight-finder proposes findings, then an independent critic vets each one before it
          appears.
        </p>
      )}
    </section>
  );
}
