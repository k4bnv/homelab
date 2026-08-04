import type { APIRoute } from "astro";
import { SITE_URL } from "@/lib/seo";

// @astrojs/sitemap generates sitemap-index.xml at build time; we just need
// to point crawlers at it here.
export const GET: APIRoute = () => {
  const body = `User-agent: *
Allow: /

Sitemap: ${SITE_URL}/sitemap-index.xml
`;
  return new Response(body, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
