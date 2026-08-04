import { Check } from "lucide-react";

/**
 * Generic 3-column "Parameter | A | B" comparison table with the winning
 * cell highlighted per row. Entity-agnostic — the page decides what rows
 * mean (GPU specs, provider terms, ...) via `lib/compareContent.ts`.
 *
 * Written as React but always rendered with no `client:*` directive, so
 * Astro server-renders it to static HTML — zero client JS shipped.
 */
export interface ComparisonRow {
  label: string;
  valueA: string;
  valueB: string;
  winner: "a" | "b" | "tie";
}

interface Props {
  nameA: string;
  nameB: string;
  rows: ComparisonRow[];
}

function Cell({ value, isWinner }: { value: string; isWinner: boolean }) {
  return (
    <td
      className={
        isWinner
          ? "bg-neon-green/10 px-4 py-3 font-mono font-semibold text-neon-green"
          : "px-4 py-3 font-mono text-slate-300"
      }
    >
      <span className="inline-flex items-center gap-1.5">
        {value}
        {isWinner && <Check size={13} className="shrink-0 text-neon-green" aria-label="Winner" />}
      </span>
    </td>
  );
}

export default function SideBySideTable({ nameA, nameB, rows }: Props) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead>
          <tr className="border-b border-surface-700 text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3 font-medium">Parameter</th>
            <th className="px-4 py-3 font-medium">{nameA}</th>
            <th className="px-4 py-3 font-medium">{nameB}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-800">
          {rows.map((row) => (
            <tr key={row.label}>
              <td className="px-4 py-3 text-slate-500">{row.label}</td>
              <Cell value={row.valueA} isWinner={row.winner === "a"} />
              <Cell value={row.valueB} isWinner={row.winner === "b"} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
