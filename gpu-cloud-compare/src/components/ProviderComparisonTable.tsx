import { ExternalLink, Star, Zap } from "lucide-react";
import type { ComputedOffer, GPU } from "@/types";

/**
 * Static provider comparison table for a `/gpu/[slug]` page.
 *
 * This is a React component, but it is only ever imported into an .astro
 * page WITHOUT a `client:*` directive — Astro server-renders it to plain
 * HTML at build time and ships zero JavaScript for it. Sorting is done
 * once, at build time, by the caller (see `getComputedOffersForGpu`).
 */

function formatUsd(value: number, digits = 2): string {
  return `$${value.toFixed(digits)}`;
}

function RatingStars({ rating }: { rating: number }) {
  const rounded = Math.round(rating);
  return (
    <span className="flex items-center gap-0.5" aria-label={`${rating.toFixed(1)} out of 5 stars`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          size={11}
          className={i < rounded ? "fill-neon-green text-neon-green" : "text-surface-600"}
        />
      ))}
    </span>
  );
}

interface Props {
  gpu: GPU;
  /** Offers for this GPU, pre-sorted ascending by on-demand price. */
  offers: ComputedOffer[];
}

export default function ProviderComparisonTable({ gpu, offers }: Props) {
  if (offers.length === 0) {
    return (
      <div className="card p-6 text-center text-sm text-slate-500">
        No providers currently list the {gpu.name}.
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="border-b border-surface-700 text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3 font-medium">Provider</th>
            <th className="px-4 py-3 font-medium">On-Demand</th>
            <th className="px-4 py-3 font-medium">Spot</th>
            <th className="px-4 py-3 font-medium">Storage</th>
            <th className="px-4 py-3 font-medium">Egress</th>
            <th className="px-4 py-3 font-medium text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-800">
          {offers.map((offer) => (
            <tr key={offer.slug} className="align-top transition-colors hover:bg-surface-800/50">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span aria-hidden="true">{offer.logo_emoji}</span>
                  <div>
                    <div className="font-semibold text-slate-100">{offer.name}</div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
                      <RatingStars rating={offer.rating} />
                      {offer.rating.toFixed(1)} ({offer.review_count.toLocaleString()})
                    </div>
                  </div>
                </div>
              </td>

              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-semibold text-slate-100">
                    {formatUsd(offer.price_on_demand)}
                    <span className="text-xs font-normal text-slate-500">/hr</span>
                  </span>
                  {offer.is_best_price && (
                    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-neon-green/50 bg-neon-green/10 px-2 py-0.5 text-[10px] font-semibold text-neon-green shadow-neon-green">
                      <Zap size={10} /> Best Value
                    </span>
                  )}
                </div>
              </td>

              <td className="px-4 py-3">
                {offer.price_spot !== null ? (
                  <span className="inline-flex items-center rounded-full border border-neon-blue/40 bg-neon-blue/10 px-2 py-0.5 font-mono text-xs font-semibold text-neon-blue">
                    {formatUsd(offer.price_spot)}/hr
                  </span>
                ) : (
                  <span className="text-xs text-slate-600">Not offered</span>
                )}
              </td>

              <td className="px-4 py-3 text-xs text-slate-400">
                {formatUsd(offer.storage_cost_per_gb, 2)}
                <span className="text-slate-600">/GB/mo</span>
              </td>

              <td className="px-4 py-3 text-xs text-slate-400">
                {offer.egress_cost_per_gb === 0 ? (
                  "Free"
                ) : (
                  <>
                    {formatUsd(offer.egress_cost_per_gb, 2)}
                    <span className="text-slate-600">/GB</span>
                  </>
                )}
              </td>

              <td className="px-4 py-3 text-right">
                <a
                  href={offer.affiliate_url}
                  target="_blank"
                  rel="sponsored noopener"
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-neon-green px-3 py-1.5 text-xs font-semibold text-surface-950 transition hover:shadow-neon-green hover:brightness-110"
                >
                  Rent on {offer.name}
                  <ExternalLink size={12} />
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
