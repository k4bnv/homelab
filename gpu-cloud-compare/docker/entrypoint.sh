#!/usr/bin/env bash
set -uo pipefail

# Container entrypoint: serve the static site with nginx, and keep prices
# fresh from *inside the running container* — no GitHub Action, no external
# CI, no rebuilding/redeploying the image. Every $SYNC_INTERVAL_HOURS it
# re-runs scripts/fetch-prices.ts and rebuilds the Astro site in place.

cd /app

SYNC_INTERVAL_HOURS="${SYNC_INTERVAL_HOURS:-6}"
SYNC_INTERVAL_SECONDS=$(( SYNC_INTERVAL_HOURS * 3600 ))

log() {
  echo "[entrypoint] $(date -Iseconds) $*"
}

# Fetches live prices and rebuilds into dist.new/, then swaps it in for
# dist/ with `mv` (atomic on the same filesystem) so nginx never serves a
# half-written directory. On any failure, dist/ is left exactly as it was
# — a flaky provider API or a bad sync never takes the site down.
sync_and_rebuild() {
  log "starting price sync + rebuild"

  if npm run sync-prices && npx astro build --outDir dist.new; then
    rm -rf dist.old
    if [ -d dist ]; then mv dist dist.old; fi
    mv dist.new dist
    rm -rf dist.old
    log "rebuild complete — nginx is now serving the refreshed site (no restart needed)"
  else
    log "sync/build FAILED — keeping the currently-served dist/ untouched"
    rm -rf dist.new
  fi
}

# The image already has a dist/ baked in from `docker build` (see
# Dockerfile), so the container has something to serve immediately even
# before this fires. Re-run once on every start too, so a container that
# was stopped for a while doesn't serve stale prices until the first
# interval elapses.
sync_and_rebuild

# Background refresh loop. Runs for the life of the container; killed
# automatically when the container stops (nginx below is PID 1's foreground
# process, so `docker stop` sends it SIGTERM directly).
(
  while true; do
    sleep "$SYNC_INTERVAL_SECONDS"
    sync_and_rebuild
  done
) &

log "starting nginx (price sync every ${SYNC_INTERVAL_HOURS}h)"
exec nginx -g "daemon off;"
