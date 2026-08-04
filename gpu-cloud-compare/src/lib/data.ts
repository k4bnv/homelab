import "@/lib/loadEnv";
import gpusJson from "@/data/gpus.json";
import providersJson from "@/data/providers.json";
import useCasesJson from "@/data/use-cases.json";
import type { ComputedOffer, GPU, Provider, UseCase } from "@/types";

// `satisfies` (not `as`) so a shape mismatch in the JSON fixtures fails
// `astro check` instead of silently widening to `any`.
export const gpus = gpusJson as GPU[];
export const useCases = useCasesJson as UseCase[];

/**
 * Lets `affiliate_url` be overridden per-provider via env vars, so a
 * self-hoster can drop in their own referral links (a `.env` file, a
 * shell export, or a `docker-compose.yaml` `environment:` entry) without
 * editing/committing `providers.json`. Convention: `AFFILIATE_URL_<SLUG>`,
 * slug uppercased with hyphens as underscores — e.g. provider slug
 * "vast-ai" → env var `AFFILIATE_URL_VAST_AI`. Unset or empty falls back
 * to the placeholder URL already committed in the JSON fixture.
 */
function affiliateUrlEnvVar(slug: string): string {
  return `AFFILIATE_URL_${slug.toUpperCase().replace(/-/g, "_")}`;
}

function applyAffiliateOverrides(rawProviders: Provider[]): Provider[] {
  return rawProviders.map((p) => {
    const override = process.env[affiliateUrlEnvVar(p.slug)];
    return override ? { ...p, affiliate_url: override } : p;
  });
}

export const providers = applyAffiliateOverrides(providersJson as Provider[]);

const gpuById = new Map(gpus.map((g) => [g.id, g]));

export function getAllGpus(): GPU[] {
  return gpus;
}

export function getGpuById(id: string): GPU | undefined {
  return gpuById.get(id);
}

export function getAllProviders(): Provider[] {
  // dedupe by slug for provider-level pages (a provider has one row per GPU offer)
  const seen = new Set<string>();
  return providers.filter((p) => {
    if (seen.has(p.slug)) return false;
    seen.add(p.slug);
    return true;
  });
}

export function getProviderBySlug(slug: string): Provider | undefined {
  return providers.find((p) => p.slug === slug);
}

export function getOffersForGpu(gpuId: string): Provider[] {
  return providers.filter((p) => p.gpu_id === gpuId);
}

export function getOffersForProvider(providerSlug: string): Provider[] {
  return providers.filter((p) => p.slug === providerSlug);
}

/** $/hr per GB of VRAM — the core normalized metric used for sorting/badges. */
export function pricePerVramHr(provider: Provider, gpu: GPU): number {
  return provider.price_on_demand / gpu.vram_gb;
}

export function formatUsd(value: number, digits = 2): string {
  return `$${value.toFixed(digits)}`;
}

/**
 * Coarse "Xh ago" label for a `GpuMarketSnapshot.last_updated` timestamp.
 * This is a static site — the string is computed once at build time, not
 * live in the browser, so it reflects "time since the last sync + deploy",
 * not real wall-clock time for the visitor.
 */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const diffMs = now.getTime() - new Date(iso).getTime();
  const diffMin = Math.round(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

/**
 * Every (provider, gpu) offer joined with its GPU record and enriched with
 * the normalized $/VRAM/hr metric + a `is_best_price` flag (lowest
 * on-demand price for that specific GPU across all providers).
 */
export function getAllComputedOffers(): ComputedOffer[] {
  const bestPriceByGpu = new Map<string, number>();
  for (const p of providers) {
    const current = bestPriceByGpu.get(p.gpu_id);
    if (current === undefined || p.price_on_demand < current) {
      bestPriceByGpu.set(p.gpu_id, p.price_on_demand);
    }
  }

  return providers
    .map((p) => {
      const gpu = getGpuById(p.gpu_id);
      if (!gpu) return null;
      const offer: ComputedOffer = {
        ...p,
        gpu,
        price_per_vram_hr: pricePerVramHr(p, gpu),
        is_best_price: bestPriceByGpu.get(p.gpu_id) === p.price_on_demand,
      };
      return offer;
    })
    .filter((o): o is ComputedOffer => o !== null);
}

export function getComputedOffersForGpu(gpuId: string): ComputedOffer[] {
  return getAllComputedOffers()
    .filter((o) => o.gpu_id === gpuId)
    .sort((a, b) => a.price_on_demand - b.price_on_demand);
}

export function getBestOfferForGpu(gpuId: string): ComputedOffer | undefined {
  return getComputedOffersForGpu(gpuId)[0];
}

/** Cheapest on-demand offer per provider, used for provider detail pages. */
export function getComputedOffersForProvider(slug: string): ComputedOffer[] {
  return getAllComputedOffers()
    .filter((o) => o.slug === slug)
    .sort((a, b) => a.price_per_vram_hr - b.price_per_vram_hr);
}

/** Average on-demand $/hr for a GPU across every provider that rents it. Used on /compare pages. */
export function getAveragePriceForGpu(gpuId: string): number {
  const offers = getOffersForGpu(gpuId);
  if (offers.length === 0) return 0;
  return offers.reduce((sum, o) => sum + o.price_on_demand, 0) / offers.length;
}

/** Average spot $/hr for a GPU across providers that offer spot pricing for it, or null if none do. */
export function getAverageSpotPriceForGpu(gpuId: string): number | null {
  const spotOffers = getOffersForGpu(gpuId).filter(
    (o): o is Provider & { price_spot: number } => o.price_spot !== null
  );
  if (spotOffers.length === 0) return null;
  return spotOffers.reduce((sum, o) => sum + o.price_spot, 0) / spotOffers.length;
}

/** Average $/GB VRAM/hr for a GPU, based on its average on-demand price. */
export function getAveragePricePerVramHr(gpu: GPU): number {
  const avgPrice = getAveragePriceForGpu(gpu.id);
  return gpu.vram_gb > 0 ? avgPrice / gpu.vram_gb : 0;
}

/** Cheapest on-demand $/hr a provider charges across every GPU it offers — its "entry price". */
export function getMinPriceForProvider(slug: string): number {
  const offers = getOffersForProvider(slug);
  if (offers.length === 0) return 0;
  return Math.min(...offers.map((o) => o.price_on_demand));
}

export function getUseCaseBySlug(slug: string): UseCase | undefined {
  return useCases.find((u) => u.slug === slug);
}

export function getGpusForUseCase(useCase: UseCase): GPU[] {
  return useCase.recommended_gpu_ids
    .map((id) => getGpuById(id))
    .filter((g): g is GPU => g !== undefined);
}

/** Formats a URL-safe id ("nvidia-h100") into a readable label ("Nvidia H100") fallback. */
export function humanize(id: string): string {
  return id
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
