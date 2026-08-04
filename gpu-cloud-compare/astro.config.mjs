import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import tailwind from "@astrojs/tailwind";
import sitemap from "@astrojs/sitemap";

// Production domain for this pSEO site. Update once the subdomain is live
// (e.g. https://gpu.kolyachaba.top) — sitemap.xml / canonical / OG tags key off this.
const SITE_URL = "https://gpu-cloud-compare.example.com";

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
