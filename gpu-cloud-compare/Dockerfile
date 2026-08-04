# Self-hosted GPU Cloud Compare: one container, no external CI. nginx
# serves the static Astro build; docker/entrypoint.sh re-syncs prices and
# rebuilds in place on a schedule (default every 6h — see
# SYNC_INTERVAL_HOURS in docker-compose.yaml). See README.md's "Self-hosting
# with Docker" section for the full picture.
FROM node:20-alpine

# bash: entrypoint.sh readability. nginx: serves the built dist/.
RUN apk add --no-cache bash nginx

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Bake a first snapshot into the image so `docker run` has something to
# serve immediately, before the runtime sync loop has fired even once.
# This is the only build that runs `astro check` — a broken build fails
# `docker build`, not a container that's already live.
RUN npm run build

COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV SYNC_INTERVAL_HOURS=6
EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
