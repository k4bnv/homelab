# GPU Cloud Compare

Programmatic-SEO price comparison site for GPU cloud rental (RunPod, Vast.ai,
TensorDock, Lambda Labs, CoreWeave). Astro + React islands + Tailwind, fully
static (SSG), built for speed, mobile-first layout and affiliate-link
conversion.

> Pet project — see the [homelab repo root](../README.md) for how this fits
> into the wider portfolio.

## Stack

- **Framework:** [Astro](https://astro.build) (static output) + React islands
  for the interactive parts only (filter table, breadcrumbs stay zero-JS)
- **Styling:** Tailwind CSS, dark-mode-by-default, neon green/blue accents
- **Icons:** [lucide-react](https://lucide.dev)
- **UI primitives:** hand-rolled shadcn-style components (`src/components/ui`)
- **Data:** static JSON fixtures in `src/data/`, no database, no API calls at
  request time — everything is resolved at build time for SSG

## Data model

| File | Shape | Purpose |
|---|---|---|
| `src/data/gpus.json` | `GPU[]` | GPU specs (VRAM, architecture, target tasks) |
| `src/data/providers.json` | `Provider[]` | One row per (provider, GPU) rental offer |
| `src/data/use-cases.json` | `UseCase[]` | Task bundles that drive `/best-gpu-for/*` |

Types live in `src/types/index.ts`. `src/lib/data.ts` is the only place that
reads the JSON files and joins them (`getAllComputedOffers`,
`getComputedOffersForGpu`, …) — pages never touch the JSON directly.

**All prices, ratings and affiliate URLs in this repo are placeholder test
data** for scaffolding purposes — wire up real pricing (scraper, provider
APIs, or a manually-updated spreadsheet export) before shipping to
production, and replace every `?ref=AFFILIATE_ID` with real affiliate links.

## Routes

| Route | Generation | Purpose |
|---|---|---|
| `/` | static | Filterable/sortable comparison table of every GPU |
| `/gpu/[slug]/` | `getStaticPaths` over `gpus.json` | Per-GPU provider comparison + FAQ (Product/AggregateRating/FAQPage schema) |
| `/compare/[a]-vs-[b]/` | `getStaticPaths` over all GPU pairs + all provider pairs | Head-to-head spec/price table + verdict |
| `/best-gpu-for/[use-case]/` | `getStaticPaths` over `use-cases.json` | Ranked GPU picks for a task (LLM training, ComfyUI, …) |
| `/robots.txt` | endpoint | Points crawlers at the sitemap |
| `/sitemap-index.xml` | `@astrojs/sitemap` | Auto-generated at build time |

## SEO

- Per-page `<title>`, meta description, canonical URL, OpenGraph + Twitter
  Card tags via `src/components/SeoHead.astro` (`src/lib/seo.ts`)
- JSON-LD: `Product` + `AggregateRating` on GPU pages, `FAQPage` on every FAQ
  block, `BreadcrumbList` on every page with breadcrumbs
  (`src/lib/schema.ts`, dropped in via `src/components/JsonLd.astro`)
- `sitemap.xml` + `robots.txt` generated automatically at build

## Performance choices

- Static output (`output: "static"` in `astro.config.mjs`) — every route is
  plain HTML at build time, no server round-trip
- Only the homepage filter table hydrates as a client island
  (`client:load` on `<GpuFilterTable />`); everything else (badges,
  breadcrumbs, FAQ accordions, CTA buttons) ships zero JavaScript
- `compressHTML: true` + `inlineStylesheets: "auto"` in Astro config

## Local development

```bash
cd gpu-cloud-compare
npm install
npm run dev        # http://localhost:4321
npm run build       # astro check + static build -> dist/
npm run preview     # serve the production build locally
```

## Extending

- **Add a GPU:** append to `src/data/gpus.json`, then add matching offers to
  `providers.json` — `/gpu/[slug]`, the homepage table and every
  `/compare/*` pair page regenerate automatically.
- **Add a provider:** append offer rows to `providers.json` with a new
  `slug`; provider-vs-provider comparison pages are generated for every pair
  automatically by `src/lib/comparisons.ts`.
- **Add a use case:** append to `use-cases.json` with a `recommended_gpu_ids`
  list; `/best-gpu-for/[slug]` and its FAQ are generated automatically.
- **Real pricing data:** replace the static JSON read in `src/lib/data.ts`
  with a build-time fetch (e.g. a script that pulls provider APIs into
  `src/data/*.json` before `astro build` runs in CI).
