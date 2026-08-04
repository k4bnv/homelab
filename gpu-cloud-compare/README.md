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

**Ratings and review counts are still placeholder test data.** Pricing
(`price_on_demand`, `price_spot`) is kept live by `npm run sync-prices` —
see below. Affiliate URLs default to a `?ref=AFFILIATE_ID` placeholder but
are meant to be overridden via environment variables, not hand-edited in
the JSON — see **[Affiliate links](#affiliate-links)**.

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

Two ways to keep this running on a schedule — pick one:

### Option A — Self-hosted Docker (no CI, no GitHub required)

See **[Self-hosting with Docker](#self-hosting-with-docker)** below. The
container re-syncs and rebuilds itself on an interval — nothing needs to
push to `main` or run in GitHub Actions.

### Option B — Static host + GitHub Actions (`.github/workflows/daily-sync.yml`)

For deploying to Vercel/Netlify/Cloudflare Pages instead: the workflow runs
`sync-prices` every 6 hours (plus on-demand via `workflow_dispatch`) and
commits `src/data/*.json` straight to `main` when prices actually changed,
which triggers the host's normal git-push auto-deploy. Configure in the
repo's Actions secrets:

- `RUNPOD_API_KEY` — optional, enables the RunPod fetcher.
- `DEPLOY_HOOK_URL` — optional, a platform deploy hook POSTed after a
  successful price commit (useful if the host doesn't auto-deploy on push).
  Skipped (not failed) if unset.

You don't need both — if you're self-hosting with Docker, you can disable
or delete this workflow.

## Configuration via environment variables

Both of these are read once at build time (`src/lib/loadEnv.ts` +
`src/lib/seo.ts` / `src/lib/data.ts`, and `astro.config.mjs` for
`SITE_URL` specifically) and baked into every generated page — there's no
client-side lookup, so they work identically however you build. Copy
[`.env.example`](.env.example) to `.env` and fill in what you need:

```bash
cp .env.example .env
```

- **Docker (recommended for self-hosting):** put `.env` next to
  `docker-compose.yaml` — Compose reads it automatically for the entries
  already wired into the `environment:` block, so it's picked up on every
  `docker compose up -d --build` and on every in-container resync (see
  below).
- **Local `npm run dev` / `npm run build`:** the same `.env` at the
  project root works too — a small dependency-free loader
  (`src/lib/loadEnv.ts`) reads it into `process.env` (Astro/Vite's own
  dotenv handling only exposes `PUBLIC_`-prefixed vars to build code,
  which these deliberately aren't, so this project loads the file
  itself instead).
- **CI (`.github/workflows/daily-sync.yml`):** set these as real repo
  Actions secrets/variables and pass them through to the sync step the
  same way `RUNPOD_API_KEY` is, if you're using that path instead.

### Site domain

`SITE_URL` controls the domain baked into `sitemap.xml`, every page's
`<link rel="canonical">`, and OpenGraph/Twitter tags. Defaults to
`https://gpu.kolyachaba.top` (both `astro.config.mjs` and
`src/lib/seo.ts` — keep them in sync if you change the default). Set it
to whatever domain you're actually deploying to:

```bash
SITE_URL=https://your-domain.example
```

### Affiliate links

Every `affiliate_url` in `src/data/providers.json` ships as a
`?ref=AFFILIATE_ID` placeholder — swap in your real referral links via
environment variables instead of editing that committed file:

```bash
# one line per provider, e.g.:
AFFILIATE_URL_RUNPOD=https://runpod.io/?ref=YOUR_REAL_ID
```

The convention is `AFFILIATE_URL_<SLUG>` — the provider's `slug` field
from `providers.json`, uppercased with hyphens as underscores (`vast-ai` →
`AFFILIATE_URL_VAST_AI`). Any provider left unset keeps the placeholder
URL; nothing breaks if you only have deals with some providers.

## Self-hosting with Docker

One container, no external CI: `docker/entrypoint.sh` re-runs
`npm run sync-prices` + rebuilds the Astro site **inside the running
container** on an interval, and nginx serves the result. Nothing pushes to
GitHub and nothing needs to redeploy the image for prices to stay fresh.

```bash
cd gpu-cloud-compare
docker compose up -d --build
```

This repo's `docker-compose.yaml` joins the shared `frontend` network used
by every other service in this homelab (see [repo root
README](../README.md)) and publishes port 8090 on the host. Traefik already
has a route configured for it at `gpu.kolyachaba.top` in
`../traefik/dynamic/services.yml` — adjust or remove that if you're hosting
elsewhere. Without Traefik, hit it directly at `http://<host>:8090`.

**How the refresh loop works** (`docker/entrypoint.sh`):

1. On container start, and then every `SYNC_INTERVAL_HOURS` (default `6`,
   set in `docker-compose.yaml`): runs `npm run sync-prices`, then
   `astro build` into `dist.new/`.
2. On success, atomically swaps `dist.new/` in for `dist/` (`mv` on the
   same filesystem) — nginx, which serves straight from `/app/dist`, never
   sees a half-written directory and needs no restart to pick up the
   change.
3. On failure (a provider API down, a bad build), the currently-served
   `dist/` is left completely untouched — a bad sync never takes the site
   offline.

Environment variables (set in `docker-compose.yaml`):

| Variable | Default | Purpose |
|---|---|---|
| `SYNC_INTERVAL_HOURS` | `6` | Hours between in-container price syncs |
| `RUNPOD_API_KEY` | unset | Optional — enables the RunPod fetcher (see above) |
| `SITE_URL` | `https://gpu.kolyachaba.top` | Domain for sitemap/canonical/OG tags, see [Site domain](#site-domain) |
| `AFFILIATE_URL_*` | unset | Optional — your real referral links, see [Affiliate links](#affiliate-links) |

Image layout: `node:20-alpine` + `nginx`, `docker build` bakes one initial
`dist/` (this is the only point `astro check` runs — a broken build fails
`docker build`, not a live container), then `docker/entrypoint.sh` takes
over both serving and the refresh loop at runtime. There's no multi-stage
slim final image, since the container needs the full Node toolchain
present at runtime to keep rebuilding, not just to serve static files.

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
