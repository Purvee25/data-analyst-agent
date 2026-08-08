// Scrollable preview of the first rows of the cleaned dataset.

import type { Preview } from "../types";

export default function PreviewTable({ preview }: { preview: Preview }) {
  return (
    <div className="card overflow-hidden">
      <div className="max-h-80 overflow-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-slate-900/95 backdrop-blur">
            <tr>
              {preview.columns.map((c) => (
                <th
                  key={c}
                  className="whitespace-nowrap border-b border-white/10 px-3 py-2 font-semibold text-slate-300"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, i) => (
              <tr key={i} className="odd:bg-white/[0.015] hover:bg-white/[0.04]">
                {preview.columns.map((c) => (
                  <td key={c} className="whitespace-nowrap px-3 py-1.5 text-slate-400">
                    {row[c] === null || row[c] === undefined ? (
                      <span className="text-slate-600">—</span>
                    ) : (
                      String(row[c])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
