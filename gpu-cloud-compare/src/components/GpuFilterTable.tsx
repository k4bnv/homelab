import { useMemo, useState } from "react";
import { ArrowUpDown, ExternalLink, Search, SlidersHorizontal, Star, Zap } from "lucide-react";
import { cn } from "@/lib/cn";
import type { TargetTask } from "@/types";

export interface GpuTableRow {
  gpuId: string;
  gpuSlug: string;
  name: string;
  vramGb: number;
  architecture: string;
  tasks: TargetTask[];
  bestPriceOnDemand: number;
  bestPriceSpot: number | null;
  bestProviderName: string;
  bestProviderUrl: string;
  pricePerVramHr: number;
  providerCount: number;
  rating: number;
}

type SortKey = "price" | "price-per-vram" | "vram" | "rating";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "price", label: "Price: Low to High" },
  { value: "price-per-vram", label: "$ / GB VRAM / hr" },
  { value: "vram", label: "VRAM: High to Low" },
  { value: "rating", label: "Rating" },
];

const ALL_TASKS: TargetTask[] = [
  "LLM Training",
  "LLM Fine-tuning",
  "LLM Inference",
  "AI Inference",
  "ComfyUI / Stable Diffusion",
  "3D Rendering",
  "Video Editing",
  "Computer Vision",
  "Scientific Computing",
];

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

interface Props {
  rows: GpuTableRow[];
}

export default function GpuFilterTable({ rows }: Props) {
  const [search, setSearch] = useState("");
  const [minVram, setMinVram] = useState(0);
  const [maxPrice, setMaxPrice] = useState(() =>
    Math.ceil(Math.max(...rows.map((r) => r.bestPriceOnDemand)))
  );
  const [task, setTask] = useState<TargetTask | "all">("all");
  const [sortKey, setSortKey] = useState<SortKey>("price");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const priceCeiling = useMemo(
    () => Math.ceil(Math.max(...rows.map((r) => r.bestPriceOnDemand))),
    [rows]
  );
  const vramCeiling = useMemo(() => Math.max(...rows.map((r) => r.vramGb)), [rows]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const result = rows.filter((row) => {
      if (term && !row.name.toLowerCase().includes(term)) return false;
      if (row.vramGb < minVram) return false;
      if (row.bestPriceOnDemand > maxPrice) return false;
      if (task !== "all" && !row.tasks.includes(task)) return false;
      return true;
    });

    result.sort((a, b) => {
      switch (sortKey) {
        case "price":
          return a.bestPriceOnDemand - b.bestPriceOnDemand;
        case "price-per-vram":
          return a.pricePerVramHr - b.pricePerVramHr;
        case "vram":
          return b.vramGb - a.vramGb;
        case "rating":
          return b.rating - a.rating;
        default:
          return 0;
      }
    });

    return result;
  }, [rows, search, minVram, maxPrice, task, sortKey]);

  const globalBestPriceId = useMemo(() => {
    if (rows.length === 0) return null;
    return rows.reduce((best, r) => (r.bestPriceOnDemand < best.bestPriceOnDemand ? r : best))
      .gpuId;
  }, [rows]);

  return (
    <div id="gpu-table" className="scroll-mt-24">
      {/* Filter bar */}
      <div className="card mb-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[180px] flex-1">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search GPU, e.g. H100"
              aria-label="Search GPUs"
              className="w-full rounded-lg border border-surface-600 bg-surface-800 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-600 focus:border-neon-green/60 focus:outline-none focus:ring-1 focus:ring-neon-green/40"
            />
          </div>

          <div className="flex items-center gap-2">
            <ArrowUpDown size={16} className="text-slate-500" />
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              aria-label="Sort by"
              className="rounded-lg border border-surface-600 bg-surface-800 px-2 py-2 text-sm text-slate-200 focus:border-neon-green/60 focus:outline-none"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => setFiltersOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
              filtersOpen
                ? "border-neon-blue/50 bg-neon-blue/10 text-neon-blue"
                : "border-surface-600 bg-surface-800 text-slate-300 hover:border-surface-500"
            )}
            aria-expanded={filtersOpen}
          >
            <SlidersHorizontal size={16} />
            Filters
          </button>

          <span className="ml-auto text-xs text-slate-500">
            {filtered.length} of {rows.length} GPUs
          </span>
        </div>

        {filtersOpen && (
          <div className="mt-4 grid gap-4 border-t border-surface-700 pt-4 sm:grid-cols-3">
            <label className="text-xs text-slate-400">
              Min VRAM: <span className="font-semibold text-slate-200">{minVram} GB</span>
              <input
                type="range"
                min={0}
                max={vramCeiling}
                step={8}
                value={minVram}
                onChange={(e) => setMinVram(Number(e.target.value))}
                className="mt-2 w-full accent-neon-green"
              />
            </label>

            <label className="text-xs text-slate-400">
              Max price: <span className="font-semibold text-slate-200">{formatUsd(maxPrice)}/hr</span>
              <input
                type="range"
                min={0}
                max={priceCeiling}
                step={0.1}
                value={maxPrice}
                onChange={(e) => setMaxPrice(Number(e.target.value))}
                className="mt-2 w-full accent-neon-green"
              />
            </label>

            <label className="text-xs text-slate-400">
              Task
              <select
                value={task}
                onChange={(e) => setTask(e.target.value as TargetTask | "all")}
                className="mt-2 w-full rounded-lg border border-surface-600 bg-surface-800 px-2 py-2 text-sm text-slate-200 focus:border-neon-green/60 focus:outline-none"
              >
                <option value="all">All tasks</option>
                {ALL_TASKS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-surface-700 text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-medium">GPU</th>
              <th className="px-4 py-3 font-medium">VRAM</th>
              <th className="px-4 py-3 font-medium">From (on-demand)</th>
              <th className="px-4 py-3 font-medium">Spot</th>
              <th className="px-4 py-3 font-medium">$/GB VRAM/hr</th>
              <th className="px-4 py-3 font-medium">Rating</th>
              <th className="px-4 py-3 font-medium">Providers</th>
              <th className="px-4 py-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-800">
            {filtered.map((row) => (
              <tr key={row.gpuId} className="transition-colors hover:bg-surface-800/50">
                <td className="px-4 py-3">
                  <a href={`/gpu/${row.gpuSlug}/`} className="font-semibold text-slate-100 hover:text-neon-green">
                    {row.name}
                  </a>
                  <div className="mt-0.5 text-xs text-slate-500">{row.architecture}</div>
                </td>
                <td className="px-4 py-3 text-slate-300">{row.vramGb} GB</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-slate-100">
                      {formatUsd(row.bestPriceOnDemand)}
                    </span>
                    {row.gpuId === globalBestPriceId && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-neon-green/50 bg-neon-green/10 px-2 py-0.5 text-[10px] font-semibold text-neon-green">
                        <Zap size={10} /> Best Price
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500">via {row.bestProviderName}</div>
                </td>
                <td className="px-4 py-3">
                  {row.bestPriceSpot !== null ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-neon-blue/40 bg-neon-blue/10 px-2 py-0.5 text-xs font-semibold text-neon-blue">
                      {formatUsd(row.bestPriceSpot)}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-400">
                  {formatUsd(row.pricePerVramHr)}
                </td>
                <td className="px-4 py-3">
                  <span className="flex items-center gap-1 text-xs text-slate-300">
                    <Star size={12} className="fill-neon-green text-neon-green" />
                    {row.rating.toFixed(1)}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">{row.providerCount} providers</td>
                <td className="px-4 py-3 text-right">
                  <a
                    href={row.bestProviderUrl}
                    target="_blank"
                    rel="sponsored noopener"
                    className="inline-flex items-center gap-1 rounded-lg bg-neon-green px-3 py-1.5 text-xs font-semibold text-surface-950 transition hover:shadow-neon-green hover:brightness-110"
                  >
                    Rent for {formatUsd(row.bestPriceOnDemand)}/hr
                    <ExternalLink size={12} />
                  </a>
                </td>
              </tr>
            ))}

            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-500">
                  No GPUs match these filters. Try widening your price or VRAM range.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
