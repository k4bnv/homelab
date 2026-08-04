import gpusJson from "@/data/gpus.json";
import providersJson from "@/data/providers.json";
import useCasesJson from "@/data/use-cases.json";
import type { ComputedOffer, GPU, Provider, UseCase } from "@/types";

// `satisfies` (not `as`) so a shape mismatch in the JSON fixtures fails
// `astro check` instead of silently widening to `any`.
export const gpus = gpusJson as GPU[];
export const providers = providersJson as Provider[];
export const useCases = useCasesJson as UseCase[];

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
