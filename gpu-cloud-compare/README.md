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
| `/gpu/[slug]/` | `getStaticPaths` over `gpus.json` | Per-GPU provider comparison, cost calculator + FAQ (Product/AggregateRating/FAQPage schema) |
| `/compare/[a]-vs-[b]/` | `getStaticPaths` over comparable GPU pairs + all provider pairs (`src/utils/pseo.ts`) | AI Verdict, side-by-side spec table, pros/cons, cost efficiency, FAQ |
| `/compare/` | static | Hub page linking every generated comparison |
| `/best-gpu-for/[use-case]/` | `getStaticPaths` over `use-cases.json` | Ranked GPU picks for a task (LLM training, ComfyUI, …) |
| `/robots.txt` | endpoint | Points crawlers at the sitemap |
| `/sitemap-index.xml` | `@astrojs/sitemap` | Auto-generated at build time |

## Programmatic comparisons (`/compare/`)

`src/utils/pseo.ts` is the single source of truth for what `/compare/`
pages exist:

- `generateGpuPairs()` — every GPU pair worth comparing (`areGpusComparable`
  filters to same-vendor cards within a ~4x VRAM tier or with overlapping
  target tasks, so the catalog won't generate nonsense pairs as it grows).
- `generateProviderPairs()` — every provider pair (no filter; any two
  providers are worth comparing).
- `canonicalPairSlug(idA, idB)` — always alphabetically orders the two ids,
  so `h100-vs-a100` and `a100-vs-h100` can never both exist as separate
  pages. Every place that links to a `/compare/` page (footer, GPU detail
  page, the compare page's own "related comparisons") goes through this.
- `resolveComparison(slug)` — parses `[a]-vs-[b]` back into a typed GPU or
  Provider pair for the page to render; `isValidPairSlug()` wraps it as a
  boolean check.

`src/lib/compareContent.ts` builds all the templated copy for a pair (side-
by-side table rows with a computed row "winner", the AI Verdict one-liner,
pros/cons, and 3 FAQ items) purely from the GPU/Provider records — no
hand-written copy per page.

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
  automatically by `src/utils/pseo.ts`.
- **Add a use case:** append to `use-cases.json` with a `recommended_gpu_ids`
  list; `/best-gpu-for/[slug]` and its FAQ are generated automatically.
- **Real pricing data:** replace the static JSON read in `src/lib/data.ts`
  with a build-time fetch (e.g. a script that pulls provider APIs into
  `src/data/*.json` before `astro build` runs in CI).
