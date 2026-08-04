import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

/**
 * Minimal, dependency-free ".env" loader for local `astro dev`/`astro
 * build` runs. Astro/Vite's own dotenv handling only exposes
 * `PUBLIC_`-prefixed vars to `import.meta.env` and doesn't sync arbitrary
 * names into `process.env`, so a plain var like `AFFILIATE_URL_RUNPOD` or
 * `SITE_URL` in a project-root `.env` file wouldn't otherwise be visible
 * to server-side code. Real environment variables (Docker `environment:`,
 * CI secrets, a shell `export`) already land in `process.env` without
 * this — this only fills the gap for a local `.env` file, and never
 * overrides a var that's already set for real.
 *
 * Importing this module for its side effect is idempotent — every caller
 * (`lib/data.ts`, `lib/seo.ts`, ...) can import it regardless of load
 * order, since an already-set key is always left untouched.
 *
 * `astro.config.mjs` needs the identical logic but can't import this file
 * (it runs as plain Node before Vite/TS exist), so it keeps its own small
 * copy — if you change the parsing rules here, update that copy too.
 */
function loadDotEnvIntoProcessEnv(): void {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!existsSync(envPath)) return;

  for (const line of readFileSync(envPath, "utf-8").split("\n")) {
    const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    if (key.startsWith("#") || process.env[key] !== undefined) continue;
    process.env[key] = rawValue.replace(/^(['"])(.*)\1$/, "$2"); // strip surrounding quotes
  }
}

loadDotEnvIntoProcessEnv();
