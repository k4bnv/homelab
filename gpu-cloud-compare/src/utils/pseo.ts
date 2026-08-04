import { gpus, providers } from "@/lib/data";
import type { GPU, Provider } from "@/types";

/**
 * Programmatic-SEO utilities for `/compare/[pair-slug]/`: generating every
 * pair of comparable entities, building/parsing the canonical URL slug, and
 * surfacing related pairs for interlinking. This is the single source of
 * truth for what `/compare/*` pages exist — `getStaticPaths` and the page's
 * own slug resolution both go through here so they can never drift apart.
 */

const PAIR_SEPARATOR = "-vs-";

export interface GpuPair {
  type: "gpu";
  a: GPU;
  b: GPU;
  slug: string;
}

export interface ProviderPair {
  type: "provider";
  a: Provider;
  b: Provider;
  slug: string;
}

export type EntityPair = GpuPair | ProviderPair;

export type ResolvedComparison =
  | { type: "gpu-vs-gpu"; slug: string; a: GPU; b: GPU }
  | { type: "provider-vs-provider"; slug: string; a: Provider; b: Provider };

/**
 * Canonical `/compare/[slug]` for any two ids — always alphabetically
 * ordered so `"h100-vs-a100"` and `"a100-vs-h100"` resolve to the exact
 * same, single generated page instead of creating a duplicate-content pair.
 */
export function canonicalPairSlug(idA: string, idB: string): string {
  const [a, b] = [idA, idB].sort((x, y) => x.localeCompare(y));
  return `${a}${PAIR_SEPARATOR}${b}`;
}

/** All unique unordered pairs from a list, alphabetically ordered for a stable canonical slug. */
function uniquePairs<T>(items: T[], keyOf: (item: T) => string): [T, T][] {
  const sorted = [...items].sort((x, y) => keyOf(x).localeCompare(keyOf(y)));
  const pairs: [T, T][] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      pairs.push([sorted[i], sorted[j]]);
    }
  }
  return pairs;
}

/**
 * Two GPUs are worth a dedicated comparison page when they're in the same
 * rental "class": same vendor, and either a similar VRAM tier (within 4x)
 * or overlapping target tasks. This keeps pSEO output relevant as the
 * catalog grows — e.g. it won't generate a 4GB laptop GPU vs. an H100 pod —
 * while every pair in the current 5-card catalog satisfies it today.
 */
export function areGpusComparable(a: GPU, b: GPU): boolean {
  if (a.id === b.id) return false;
  if (a.vendor !== b.vendor) return false;
  const vramRatio = Math.max(a.vram_gb, b.vram_gb) / Math.min(a.vram_gb, b.vram_gb);
  const sharesTask = a.target_tasks.some((t) => b.target_tasks.includes(t));
  return vramRatio <= 4 || sharesTask;
}

/** Every GPU-vs-GPU pair worth generating a page for. */
export function generateGpuPairs(list: GPU[] = gpus): GpuPair[] {
  return uniquePairs(list, (g) => g.id)
    .filter(([a, b]) => areGpusComparable(a, b))
    .map(([a, b]) => ({ type: "gpu", a, b, slug: canonicalPairSlug(a.id, b.id) }));
}

/** Every provider-vs-provider pair — all providers are comparable, no filter needed. */
export function generateProviderPairs(list: Provider[] = providers): ProviderPair[] {
  const uniqueProviders = [...new Map(list.map((p) => [p.slug, p])).values()];
  return uniquePairs(uniqueProviders, (p) => p.slug).map(([a, b]) => ({
    type: "provider",
    a,
    b,
    slug: canonicalPairSlug(a.slug, b.slug),
  }));
}

export function getAllComparisonPairs(): EntityPair[] {
  return [...generateGpuPairs(), ...generateProviderPairs()];
}

/** Every `/compare/[slug]` page we statically generate — feeds `getStaticPaths`. */
export function getAllComparisonSlugs(): string[] {
  return getAllComparisonPairs().map((pair) => pair.slug);
}

/**
 * Parses a `[a]-vs-[b]` slug. GPU ids and provider slugs both contain
 * hyphens (e.g. "nvidia-rtx-4090", "lambda-labs") so we can't just split on
 * "-vs-" blindly — we try every "-vs-" occurrence as the split point until
 * both halves resolve against a known GPU or provider.
 */
export function resolveComparison(slug: string): ResolvedComparison | null {
  const gpuById = new Map(gpus.map((g) => [g.id, g]));
  const providerBySlug = new Map(providers.map((p) => [p.slug, p]));

  let searchFrom = 0;
  while (true) {
    const idx = slug.indexOf(PAIR_SEPARATOR, searchFrom);
    if (idx === -1) return null;

    const left = slug.slice(0, idx);
    const right = slug.slice(idx + PAIR_SEPARATOR.length);

    const gpuA = gpuById.get(left);
    const gpuB = gpuById.get(right);
    if (gpuA && gpuB) {
      return { type: "gpu-vs-gpu", slug, a: gpuA, b: gpuB };
    }

    const providerA = providerBySlug.get(left);
    const providerB = providerBySlug.get(right);
    if (providerA && providerB) {
      return { type: "provider-vs-provider", slug, a: providerA, b: providerB };
    }

    searchFrom = idx + 1;
  }
}

/** True if `slug` resolves to a real, statically-generated `/compare/` page. */
export function isValidPairSlug(slug: string): boolean {
  return resolveComparison(slug) !== null;
}

export interface RelatedComparison {
  slug: string;
  label: string;
}

/**
 * Up to `limit` other GPU comparison pages that share GPU A or GPU B with
 * the current pair — e.g. from `h100-vs-a100`, suggests `h100-vs-l40s` and
 * `a100-vs-rtx-4090`. Interleaves matches for A and B so the result isn't
 * dominated by just one side. Powers "Other Popular Comparisons".
 */
export function getRelatedGpuComparisons(
  currentSlug: string,
  idA: string,
  idB: string,
  limit = 6
): RelatedComparison[] {
  const others = generateGpuPairs().filter((p) => p.slug !== currentSlug);
  const withA = others.filter((p) => p.a.id === idA || p.b.id === idA);
  const withB = others.filter((p) => p.a.id === idB || p.b.id === idB);
  return interleavePairs(withA, withB, limit);
}

/** Same idea as `getRelatedGpuComparisons`, for provider-vs-provider pairs. */
export function getRelatedProviderComparisons(
  currentSlug: string,
  slugA: string,
  slugB: string,
  limit = 6
): RelatedComparison[] {
  const others = generateProviderPairs().filter((p) => p.slug !== currentSlug);
  const withA = others.filter((p) => p.a.slug === slugA || p.b.slug === slugA);
  const withB = others.filter((p) => p.a.slug === slugB || p.b.slug === slugB);
  return interleavePairs(withA, withB, limit);
}

function interleavePairs<T extends EntityPair>(withA: T[], withB: T[], limit: number): RelatedComparison[] {
  const merged: T[] = [];
  const seen = new Set<string>();
  const max = Math.max(withA.length, withB.length);
  for (let i = 0; i < max && merged.length < limit; i++) {
    for (const candidate of [withA[i], withB[i]]) {
      if (candidate && !seen.has(candidate.slug) && merged.length < limit) {
        seen.add(candidate.slug);
        merged.push(candidate);
      }
    }
  }
  return merged.map((p) => ({ slug: p.slug, label: `${p.a.name} vs ${p.b.name}` }));
}
