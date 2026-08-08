// Natural-language follow-up chat with session memory (handled server-side) and
// inline auto-charts. Each answer may carry a ChartData the backend computed.

import { useRef, useState } from "react";
import { askQuestion } from "../api";
import type { ChartData } from "../types";
import Chart from "./Chart";
import TypedText from "./TypedText";

interface Turn {
  role: "user" | "assistant";
  text: string;
  chart?: ChartData | null;
}

const SUGGESTIONS = [
  "Which region has the highest profit?",
  "Show sales by category",
  "How does profit trend over time?",
];

export default function QAPanel({
  sessionId,
  onRequestUsed,
}: {
  sessionId: string;
  onRequestUsed: (n: number) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function send(question: string) {
    const q = question.trim();
    if (!q || loading) return;
    setError(null);
    setTurns((t) => [...t, { role: "user", text: q }]);
    setInput("");
    setLoading(true);
    try {
      const res = await askQuestion(sessionId, q);
      setTurns((t) => [...t, { role: "assistant", text: res.answer, chart: res.chart }]);
      onRequestUsed(res.requests_used);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 1e9, behavior: "smooth" }));
    }
  }

  return (
    <div className="card flex flex-col p-5">
      <h3 className="mb-3 text-lg font-semibold text-slate-100">💬 Ask a follow-up</h3>

      <div ref={scrollRef} className="mb-3 max-h-[26rem] space-y-3 overflow-y-auto pr-1">
        {turns.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-500/90 px-4 py-2 text-sm text-white">
                {t.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex flex-col">
              <div className="max-w-[92%] rounded-2xl rounded-bl-sm bg-white/5 px-4 py-2.5 text-sm leading-relaxed text-slate-200">
                {i === turns.length - 1 ? <TypedText text={t.text} /> : t.text}
              </div>
              {t.chart && <Chart data={t.chart} />}
            </div>
          )
        )}

        {loading && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-400" />
            Analyzing…
          </div>
        )}
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Which sub-category loses the most money?"
          className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-400/50 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-xl bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
