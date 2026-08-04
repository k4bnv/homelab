import "@/lib/loadEnv";
import type { SeoMeta } from "@/types";

export const SITE_NAME = "GPUCompare.cloud";
/** Override via SITE_URL env var (.env, shell export, or docker-compose.yaml) — see astro.config.mjs, which reads the same var for `site:`. */
export const SITE_URL = process.env.SITE_URL || "https://gpucompare.cloud";
export const DEFAULT_OG_IMAGE = "/og-default.svg";

/** Builds the fully-qualified canonical URL for a given path. */
export function canonicalUrl(path: string): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${SITE_URL}${clean}`;
}

export function pageTitle(title: string): string {
  return title.includes(SITE_NAME) ? title : `${title} | ${SITE_NAME}`;
}

export function buildMeta(meta: Omit<SeoMeta, "title"> & { title: string }): SeoMeta {
  return {
    ...meta,
    title: pageTitle(meta.title),
    ogImage: meta.ogImage ?? DEFAULT_OG_IMAGE,
    type: meta.type ?? "website",
  };
}
