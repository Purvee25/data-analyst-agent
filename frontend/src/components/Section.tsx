// Simple collapsible section used for the data-quality report and preview,
// so the dashboard defaults to a clean view and details expand on demand.

import { useState, type ReactNode } from "react";

export default function Section({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left text-sm font-semibold text-slate-200 transition hover:bg-white/[0.03]"
      >
        <span>{title}</span>
        <span className={`text-slate-400 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && <div className="border-t border-white/5 p-5">{children}</div>}
    </div>
  );
}
