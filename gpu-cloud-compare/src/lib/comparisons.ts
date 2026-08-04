import { gpus, providers, getGpuById, getProviderBySlug } from "@/lib/data";
import type { GPU, Provider } from "@/types";

export interface GpuVsGpuComparison {
  type: "gpu-vs-gpu";
  slug: string;
  a: GPU;
  b: GPU;
}

export interface ProviderVsProviderComparison {
  type: "provider-vs-provider";
  slug: string;
  a: Provider;
  b: Provider;
}

export type AnyComparison = GpuVsGpuComparison | ProviderVsProviderComparison;

function pairSlug(aId: string, bId: string): string {
  return `${aId}-vs-${bId}`;
}

/** All unique unordered pairs from a list, alphabetically ordered for a stable canonical slug. */
function uniquePairs<T>(items: T[], keyOf: (item: T) => string): [T, T][] {
  const sorted = [...items].sort((a, b) => keyOf(a).localeCompare(keyOf(b)));
  const pairs: [T, T][] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      pairs.push([sorted[i], sorted[j]]);
    }
  }
  return pairs;
}

/** Every /compare/[slug] page we statically generate: all GPU pairs + all provider pairs. */
export function getAllComparisonSlugs(): string[] {
  const gpuPairs = uniquePairs(gpus, (g) => g.id).map(([a, b]) =>
    pairSlug(a.id, b.id)
  );
  const uniqueProviders = [...new Map(providers.map((p) => [p.slug, p])).values()];
  const providerPairs = uniquePairs(uniqueProviders, (p) => p.slug).map(([a, b]) =>
    pairSlug(a.slug, b.slug)
  );
  return [...gpuPairs, ...providerPairs];
}

/**
 * Parses a `[a]-vs-[b]` slug. GPU ids and provider slugs both contain
 * hyphens (e.g. "nvidia-rtx-4090", "lambda-labs") so we can't just split on
 * "-vs-" blindly — we try every "-vs-" occurrence as the split point until
 * both halves resolve against a known GPU or provider.
 */
export function resolveComparison(slug: string): AnyComparison | null {
  const marker = "-vs-";
  let searchFrom = 0;

  while (true) {
    const idx = slug.indexOf(marker, searchFrom);
    if (idx === -1) return null;

    const left = slug.slice(0, idx);
    const right = slug.slice(idx + marker.length);

    const gpuA = getGpuById(left);
    const gpuB = getGpuById(right);
    if (gpuA && gpuB) {
      return { type: "gpu-vs-gpu", slug, a: gpuA, b: gpuB };
    }

    const providerA = getProviderBySlug(left);
    const providerB = getProviderBySlug(right);
    if (providerA && providerB) {
      return { type: "provider-vs-provider", slug, a: providerA, b: providerB };
    }

    searchFrom = idx + 1;
  }
}
