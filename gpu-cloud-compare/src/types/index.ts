/**
 * Core domain types for the GPU Cloud Rental Aggregator.
 *
 * `gpus.json` and `providers.json` are validated against these shapes at
 * build time indirectly (via TS `satisfies` in src/lib/data.ts), so any
 * drift between the JSON fixtures and this file surfaces as a type error
 * during `astro check` instead of a runtime bug on a generated page.
 */

/** Canonical task tags used for filtering + `/best-gpu-for/[use-case]` routing. */
export type TargetTask =
  | "LLM Training"
  | "LLM Fine-tuning"
  | "LLM Inference"
  | "AI Inference"
  | "ComfyUI / Stable Diffusion"
  | "3D Rendering"
  | "Video Editing"
  | "Computer Vision"
  | "Scientific Computing";

export interface GPU {
  /** Stable slug used in URLs and as the FK from Provider.gpu_id, e.g. "nvidia-h100" */
  id: string;
  name: string;
  vendor: "NVIDIA" | "AMD";
  vram_gb: number;
  vram_type: "HBM3" | "HBM2e" | "GDDR6X" | "GDDR6";
  architecture: string;
  /** Thermal design power in watts, e.g. 700 */
  tdp_watts: number;
  /** Physical form factor, e.g. "SXM5", "PCIe 4.0" */
  interface: string;
  cuda_cores?: number;
  tensor_cores?: number;
  fp16_tflops?: number;
  fp8_tflops?: number;
  memory_bandwidth_gbps?: number;
  nvlink: boolean;
  release_year: number;
  target_tasks: TargetTask[];
  description: string;
  /** 1-3 short bullet points rendered on the GPU detail page */
  highlights: string[];
}

export interface Provider {
  /** Stable slug used in URLs, e.g. "runpod" */
  id: string;
  name: string;
  slug: string;
  logo_emoji: string;
  affiliate_url: string;
  /** FK -> GPU.id. One row per (provider, gpu) offer. */
  gpu_id: string;
  price_on_demand: number;
  price_spot: number | null;
  storage_cost_per_gb: number;
  egress_cost_per_gb: number;
  rating: number;
  review_count: number;
  regions: string[];
  min_billing_increment: string;
  interruption_risk: "Low" | "Medium" | "High" | "None";
  payment_model: "Marketplace" | "Reserved" | "On-Demand Cloud";
  /** "Secure" = dedicated/verified data-center hardware. "Community" = peer-to-peer/marketplace hosts. */
  cloud_type: "Secure" | "Community";
  has_api_cli: boolean;
}

/** Derived, computed at build time — never stored in JSON. */
export interface ComputedOffer extends Provider {
  gpu: GPU;
  price_per_vram_hr: number;
  is_best_price: boolean;
}

export interface UseCase {
  slug: string;
  title: string;
  short_title: string;
  description: string;
  min_vram_gb: number;
  recommended_gpu_ids: string[];
  tasks: TargetTask[];
}

export interface FaqItem {
  question: string;
  answer: string;
}

export interface Comparison {
  type: "gpu-vs-gpu" | "provider-vs-provider";
  slug: string;
  a_id: string;
  b_id: string;
  verdict: Record<string, string>;
}

/** Shape consumed by the SeoHead component on every page. */
export interface SeoMeta {
  title: string;
  description: string;
  canonicalPath: string;
  ogImage?: string;
  type?: "website" | "article";
}
