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

**Ratings, review counts and affiliate URLs are still placeholder test
data** — replace every `?ref=AFFILIATE_ID` with real affiliate links before
shipping to production. Pricing (`price_on_demand`, `price_spot`) is now
kept live by `npm run sync-prices` — see below.

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

## Live price sync (`scripts/fetch-prices.ts`)

`npm run sync-prices` polls provider pricing APIs and rewrites
`src/data/providers.json` + `src/data/gpus.json` in place, before every
`npm run build` (`"build": "npm run sync-prices && astro check && astro build"`).
It's designed to never break a build: every provider fetcher catches its own
errors and falls back to keeping the currently-committed price rather than
throwing.

| Provider | Source | Behavior without config |
|---|---|---|
| **Vast.ai** | Public `bundles` marketplace endpoint, no auth | Runs as-is; on any HTTP/network failure, keeps existing prices |
| **RunPod** | GraphQL `gpuTypes` query, requires an API key | No-ops (not an error) if `RUNPOD_API_KEY` isn't set |
| **TensorDock, Lambda Labs, CoreWeave** | No stable public pricing API | Always keeps the last committed price (documented fetcher stub — swap in a real integration per provider as one becomes available) |

`normalizeGpuName()` maps each provider's raw GPU string ("GeForce RTX 4090
24GB", "H100 SXM5", …) down to our catalog ids; anything that doesn't match
a known card is logged and skipped rather than silently dropped or
guessed. The script only ever updates a `(provider, GPU)` row that already
exists in `providers.json` — it won't auto-append an unfamiliar offer,
since it can't fill in fields like `rating` or `regions` an API doesn't
provide. `src/data/gpus.json` then gets a denormalized `market` snapshot
per GPU (min on-demand/spot price, summed live availability where a
provider reports a count, and a `last_updated` timestamp) — see
`GpuMarketSnapshot` in `src/types/index.ts`.

Required for the RunPod integration:

```bash
RUNPOD_API_KEY=...  npm run sync-prices
```

### Scheduled sync (`.github/workflows/daily-sync.yml`)

Runs `sync-prices` every 6 hours (plus on-demand via `workflow_dispatch`),
and commits `src/data/*.json` straight to `main` when prices actually
changed. Configure in the repo's Actions secrets:

- `RUNPOD_API_KEY` — optional, enables the RunPod fetcher.
- `DEPLOY_HOOK_URL` — optional, a Vercel/Netlify/Cloudflare Pages deploy
  hook POSTed after a successful price commit. Skipped (not failed) if unset.

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
npm run dev          # http://localhost:4321
npm run sync-prices  # refresh src/data/*.json from live provider APIs
npm run build        # sync-prices + astro check + static build -> dist/
npm run preview      # serve the production build locally
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
- **Wire up a real pricing API for a static-fallback provider:** add a
  `fetchXPrices()` function to `scripts/fetch-prices.ts` following the
  `fetchVastPrices`/`fetchRunPodPrices` pattern (fetch, normalize with
  `normalizeGpuName`, return `RawOffer[]`, catch-and-fallback on error) and
  add it to the `Promise.allSettled([...])` list in `main()`.
