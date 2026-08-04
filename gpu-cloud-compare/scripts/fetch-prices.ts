#!/usr/bin/env -S npx tsx
/**
 * scripts/fetch-prices.ts
 *
 * Standalone sync job: polls public GPU cloud provider APIs, normalizes
 * their GPU naming to our catalog's ids, and writes fresh prices back into
 * `src/data/providers.json` + an aggregated market snapshot into
 * `src/data/gpus.json`. Designed to run in CI (see
 * `.github/workflows/daily-sync.yml`) via `npm run sync-prices`, and to be
 * safe to run locally with zero API keys configured — every provider
 * fetcher degrades to "keep the existing committed price" on any failure
 * rather than throwing, so a flaky upstream API never breaks the build.
 *
 * Run directly: `npx tsx scripts/fetch-prices.ts`
 *
 * Deliberately dependency-free: uses Node's built-in `fetch` (Node >=18)
 * and `node:fs/promises` only, so it can't drift from whatever's installed
 * for the Astro site itself.
 */

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Relative imports only (no "@/..." alias) — this script runs standalone
// under tsx, outside Astro's Vite config, so path aliases aren't resolved.
import type { GPU, GpuMarketSnapshot, Provider } from "../src/types";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const GPUS_PATH = path.join(ROOT, "src/data/gpus.json");
const PROVIDERS_PATH = path.join(ROOT, "src/data/providers.json");

const FETCH_TIMEOUT_MS = 15_000;

// ---------------------------------------------------------------------------
// 1. GPU name normalization
// ---------------------------------------------------------------------------

/**
 * Every provider spells GPU names differently ("NVIDIA H100 80GB PCIe",
 * "H100 SXM", "Hopper H100"...). This maps a raw provider string down to a
 * short list of tokens; if the cleaned name contains any of them, it's a
 * match for that catalog id. Order matters where one pattern could be a
 * substring of another (none currently overlap in our 5-card catalog, but
 * more specific patterns are listed first as a safeguard for future GPUs).
 */
const GPU_NAME_PATTERNS: Array<{ id: string; patterns: string[] }> = [
  { id: "nvidia-rtx-a6000", patterns: ["rtx a6000", "a6000"] },
  { id: "nvidia-l40s", patterns: ["l40s", "l40 s"] },
  { id: "nvidia-rtx-4090", patterns: ["rtx 4090", "4090"] },
  { id: "nvidia-h100", patterns: ["h100"] },
  { id: "nvidia-a100", patterns: ["a100"] },
];

/**
 * Normalizes a raw provider GPU name ("GeForce RTX 4090 24GB", "NVIDIA
 * H100 80GB SXM5", "RTX4090") down to one of our catalog ids
 * ("nvidia-rtx-4090"), or `null` if it doesn't match anything we track.
 */
export function normalizeGpuName(rawName: string): string | null {
  const cleaned = rawName
    .toLowerCase()
    .replace(/nvidia|geforce|®|™/g, " ")
    .replace(/\d+\s*gb\b/g, " ") // strip VRAM-size suffixes like "24gb"
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  for (const { id, patterns } of GPU_NAME_PATTERNS) {
    if (patterns.some((p) => cleaned.includes(p))) return id;
  }
  return null;
}

// ---------------------------------------------------------------------------
// 2. Fetch helpers
// ---------------------------------------------------------------------------

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** One live (provider, GPU) price point, ready to merge into `providers.json`. */
interface RawOffer {
  providerSlug: string;
  gpuId: string;
  priceOnDemand: number;
  priceSpot: number | null;
  availableCount?: number;
}

// ---------------------------------------------------------------------------
// 3a. Vast.ai — public marketplace "bundles" (offer listing) endpoint.
//     No API key required for read access. Vast is an auction marketplace:
//     `dph_total` is the listed (on-demand) rate; `min_bid` is the lowest
//     price a spot/interruptible bid has been accepted at recently.
// ---------------------------------------------------------------------------

const VAST_BUNDLES_URL = "https://console.vast.ai/api/v0/bundles/";

interface VastOffer {
  gpu_name?: string;
  dph_total?: number;
  min_bid?: number;
  rentable?: boolean;
  num_gpus?: number;
}

async function fetchVastPrices(): Promise<RawOffer[]> {
  const providerSlug = "vast-ai";
  try {
    const res = await fetchWithTimeout(VAST_BUNDLES_URL);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} ${res.statusText}`);
    }
    const json = (await res.json()) as { offers?: VastOffer[] };
    const offers = (json.offers ?? []).filter(
      (o) => o.rentable !== false && typeof o.dph_total === "number" && (o.num_gpus ?? 1) === 1
    );

    // Group by normalized GPU id, keep the cheapest on-demand + cheapest bid per GPU.
    const byGpu = new Map<string, { onDemand: number; spot: number | null; count: number }>();
    for (const offer of offers) {
      const gpuId = normalizeGpuName(offer.gpu_name ?? "");
      if (!gpuId) continue;

      const price = offer.dph_total as number;
      const bid = typeof offer.min_bid === "number" ? offer.min_bid : null;
      const existing = byGpu.get(gpuId);
      if (!existing) {
        byGpu.set(gpuId, { onDemand: price, spot: bid, count: 1 });
      } else {
        existing.onDemand = Math.min(existing.onDemand, price);
        existing.spot = bid !== null ? Math.min(existing.spot ?? bid, bid) : existing.spot;
        existing.count += 1;
      }
    }

    return [...byGpu.entries()].map(([gpuId, agg]) => ({
      providerSlug,
      gpuId,
      priceOnDemand: round2(agg.onDemand),
      priceSpot: agg.spot !== null ? round2(agg.spot) : null,
      availableCount: agg.count,
    }));
  } catch (err) {
    console.warn(`[vast-ai] Live fetch failed, keeping existing prices for this provider: ${errorMessage(err)}`);
    return [];
  }
}

// ---------------------------------------------------------------------------
// 3b. RunPod — GraphQL catalog. `gpuTypes` is public read data, but RunPod
//     requires an API key on the request even for it, so this fetcher is a
//     no-op (not a failure) when RUNPOD_API_KEY isn't configured.
// ---------------------------------------------------------------------------

const RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql";

const RUNPOD_GPU_TYPES_QUERY = `
  query GpuTypes {
    gpuTypes {
      displayName
      lowestPrice(input: { gpuCount: 1 }) {
        minimumBidPrice
        uninterruptablePrice
      }
    }
  }
`;

interface RunPodGpuType {
  displayName?: string;
  lowestPrice?: {
    minimumBidPrice?: number | null;
    uninterruptablePrice?: number | null;
  } | null;
}

async function fetchRunPodPrices(): Promise<RawOffer[]> {
  const providerSlug = "runpod";
  const apiKey = process.env.RUNPOD_API_KEY;
  if (!apiKey) {
    console.info("[runpod] RUNPOD_API_KEY not set — skipping live fetch, keeping existing prices.");
    return [];
  }

  try {
    const res = await fetchWithTimeout(`${RUNPOD_GRAPHQL_URL}?api_key=${encodeURIComponent(apiKey)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: RUNPOD_GPU_TYPES_QUERY }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} ${res.statusText}`);
    }
    const json = (await res.json()) as { data?: { gpuTypes?: RunPodGpuType[] }; errors?: unknown[] };
    if (json.errors?.length) {
      throw new Error(`GraphQL errors: ${JSON.stringify(json.errors)}`);
    }

    const offers: RawOffer[] = [];
    for (const gpuType of json.data?.gpuTypes ?? []) {
      const gpuId = normalizeGpuName(gpuType.displayName ?? "");
      const onDemand = gpuType.lowestPrice?.uninterruptablePrice;
      if (!gpuId || typeof onDemand !== "number") continue;

      const spot = gpuType.lowestPrice?.minimumBidPrice;
      offers.push({
        providerSlug,
        gpuId,
        priceOnDemand: round2(onDemand),
        priceSpot: typeof spot === "number" ? round2(spot) : null,
      });
    }
    return offers;
  } catch (err) {
    console.warn(`[runpod] Live fetch failed, keeping existing prices for this provider: ${errorMessage(err)}`);
    return [];
  }
}

// ---------------------------------------------------------------------------
// 3c. TensorDock, Lambda Labs, CoreWeave — no stable public/unauthenticated
//     pricing API to poll. Rather than fabricate numbers, these stay on
//     their last committed price until a real integration is added; this
//     fetcher exists so the sync run + logging is consistent for every
//     provider, and so wiring up a real API later is a one-function change.
// ---------------------------------------------------------------------------

async function fetchStaticFallbackPrices(providerSlug: string): Promise<RawOffer[]> {
  console.info(`[${providerSlug}] No public pricing API integrated yet — keeping existing committed prices.`);
  return [];
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.name === "AbortError" ? `timed out after ${FETCH_TIMEOUT_MS}ms` : err.message;
  return String(err);
}

// ---------------------------------------------------------------------------
// 4. Merge live offers into providers.json, recompute gpus.json snapshot
// ---------------------------------------------------------------------------

function mergeOffersIntoProviders(
  providers: Provider[],
  rawOffers: RawOffer[],
  nowIso: string
): { providers: Provider[]; updatedCount: number; unmatched: RawOffer[] } {
  const matchedKeys = new Set<string>();

  const next = providers.map((provider) => {
    const key = `${provider.slug}:${provider.gpu_id}`;
    const match = rawOffers.find((o) => `${o.providerSlug}:${o.gpuId}` === key);
    if (!match) return provider;

    matchedKeys.add(key);
    const updated: Provider = {
      ...provider,
      price_on_demand: match.priceOnDemand,
      price_spot: match.priceSpot,
      last_updated: nowIso,
    };
    if (match.availableCount !== undefined) updated.available_count = match.availableCount;
    return updated;
  });

  const unmatched = rawOffers.filter((o) => !matchedKeys.has(`${o.providerSlug}:${o.gpuId}`));
  return { providers: next, updatedCount: matchedKeys.size, unmatched };
}

function recomputeGpuMarketSnapshots(gpus: GPU[], providers: Provider[], nowIso: string): GPU[] {
  return gpus.map((gpu) => {
    const offers = providers.filter((p) => p.gpu_id === gpu.id);
    if (offers.length === 0) return gpu;

    const onDemandPrices = offers.map((o) => o.price_on_demand);
    const spotPrices = offers.map((o) => o.price_spot).filter((p): p is number => p !== null);
    const availableCounts = offers.map((o) => o.available_count).filter((c): c is number => typeof c === "number");

    // `null`, not 0 — "no provider reported a count this run" is not the
    // same claim as "we confirmed zero instances are available".
    const market: GpuMarketSnapshot = {
      min_on_demand_price: round2(Math.min(...onDemandPrices)),
      min_spot_price: spotPrices.length > 0 ? round2(Math.min(...spotPrices)) : null,
      available_count: availableCounts.length > 0 ? availableCounts.reduce((sum, c) => sum + c, 0) : null,
      last_updated: nowIso,
    };
    return { ...gpu, market };
  });
}

// ---------------------------------------------------------------------------
// 5. Entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const nowIso = new Date().toISOString();
  console.log(`[fetch-prices] Starting GPU cloud price sync at ${nowIso}`);

  const [gpusRaw, providersRaw] = await Promise.all([
    readFile(GPUS_PATH, "utf-8"),
    readFile(PROVIDERS_PATH, "utf-8"),
  ]);
  const gpus: GPU[] = JSON.parse(gpusRaw);
  const providers: Provider[] = JSON.parse(providersRaw);

  const results = await Promise.allSettled([
    fetchVastPrices(),
    fetchRunPodPrices(),
    fetchStaticFallbackPrices("tensordock"),
    fetchStaticFallbackPrices("lambda-labs"),
    fetchStaticFallbackPrices("coreweave"),
  ]);

  const rawOffers: RawOffer[] = [];
  for (const result of results) {
    if (result.status === "fulfilled") {
      rawOffers.push(...result.value);
    } else {
      // Individual fetchers already catch + log; this is a last-resort net
      // for anything that still throws (e.g. a JSON.parse crash).
      console.error("[fetch-prices] A provider fetch rejected unexpectedly:", result.reason);
    }
  }

  const { providers: updatedProviders, updatedCount, unmatched } = mergeOffersIntoProviders(
    providers,
    rawOffers,
    nowIso
  );
  const updatedGpus = recomputeGpuMarketSnapshots(gpus, updatedProviders, nowIso);

  await writeFile(PROVIDERS_PATH, JSON.stringify(updatedProviders, null, 2) + "\n", "utf-8");
  await writeFile(GPUS_PATH, JSON.stringify(updatedGpus, null, 2) + "\n", "utf-8");

  console.log(
    `[fetch-prices] Done. ${updatedCount}/${providers.length} tracked (provider, GPU) rows refreshed from live APIs.`
  );
  if (unmatched.length > 0) {
    console.warn(
      `[fetch-prices] ${unmatched.length} live offer(s) didn't match a tracked (provider, GPU) pair and were skipped:`,
      unmatched.map((o) => `${o.providerSlug}/${o.gpuId}`).join(", ")
    );
  }
}

main().catch((err) => {
  console.error("[fetch-prices] Fatal error:", err);
  process.exitCode = 1;
});
