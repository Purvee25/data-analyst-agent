// Live "agent working" timeline. Reflects the SSE stages streamed from the
// backend so the two-agent pipeline is visible as it runs, not hidden behind a
// spinner. Each step animates from pending -> active -> complete.

export type Stage = "idle" | "summarizing" | "generating" | "critiquing" | "done" | "error";

const STEPS: { key: Stage; label: string; icon: string }[] = [
  { key: "summarizing", label: "Summarise dataset", icon: "📊" },
  { key: "generating", label: "Insight-finder (Claude call #1)", icon: "🔍" },
  { key: "critiquing", label: "Critic review (Claude call #2)", icon: "🧠" },
  { key: "done", label: "Vetted insights ready", icon: "✅" },
];

const ORDER: Stage[] = ["summarizing", "generating", "critiquing", "done"];

function statusOf(step: Stage, current: Stage): "pending" | "active" | "complete" {
  if (current === "error") return step === "summarizing" ? "complete" : "pending";
  const ci = ORDER.indexOf(current);
  const si = ORDER.indexOf(step);
  if (ci < 0) return "pending";
  if (si < ci) return "complete";
  if (si === ci) return current === "done" ? "complete" : "active";
  return "pending";
}

export default function AgentActivity({ stage, note }: { stage: Stage; note?: string }) {
  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-indigo-500" />
        </span>
        <p className="text-sm font-semibold text-slate-200">Agents at work</p>
      </div>

      <ol className="space-y-3">
        {STEPS.map((s) => {
          const st = statusOf(s.key, stage);
          return (
            <li key={s.key} className="flex items-center gap-3">
              <span
                className={`grid h-8 w-8 place-items-center rounded-full text-sm transition
                  ${st === "complete" ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40" : ""}
                  ${st === "active" ? "bg-indigo-500/20 text-indigo-200 ring-1 ring-indigo-500/50" : ""}
                  ${st === "pending" ? "bg-white/5 text-slate-500" : ""}`}
              >
                {st === "complete" ? "✓" : st === "active" ? <Spinner /> : s.icon}
              </span>
              <span
                className={`text-sm ${
                  st === "pending" ? "text-slate-500" : st === "active" ? "text-slate-100" : "text-slate-300"
                }`}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>

      {note && <p className="mt-4 text-xs text-slate-400">{note}</p>}
    </div>
  );
}

function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-300/40 border-t-indigo-300" />
  );
}
