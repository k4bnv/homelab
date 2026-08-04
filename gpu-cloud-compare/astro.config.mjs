import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import tailwind from "@astrojs/tailwind";
import sitemap from "@astrojs/sitemap";

// Same dependency-free ".env" loader as src/lib/loadEnv.ts (duplicated,
// not imported — this file runs as plain Node before Vite/TS exist, so it
// can't import a .ts module). Keep the two in sync if the parsing rules
// ever change.
function loadDotEnvIntoProcessEnv() {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!existsSync(envPath)) return;
  for (const line of readFileSync(envPath, "utf-8").split("\n")) {
    const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    if (key.startsWith("#") || process.env[key] !== undefined) continue;
    process.env[key] = rawValue.replace(/^(['"])(.*)\1$/, "$2");
  }
}
loadDotEnvIntoProcessEnv();

// Production domain for this pSEO site — sitemap.xml / canonical / OG tags
// key off this. Override via SITE_URL env var (.env, shell export, or
// docker-compose.yaml) without touching code — see src/lib/seo.ts, which
// reads the same var for canonical/OG URLs.
const SITE_URL = process.env.SITE_URL || "https://gpucompare.cloud";

export default defineConfig({
  site: SITE_URL,
  output: "static",
  integrations: [
    react(),
    tailwind({
      applyBaseStyles: false,
    }),
    sitemap({
      changefreq: "weekly",
      priority: 0.7,
    }),
  ],
  compressHTML: true,
  build: {
    inlineStylesheets: "auto",
  },
});
