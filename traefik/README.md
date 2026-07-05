# Traefik — reverse proxy + HTTPS

Automatic TLS via **Cloudflare DNS challenge** for `*.kolyachaba.top`.

| Subdomain | Service |
|-----------|---------|
| `home.kolyachaba.top` | Homepage |
| `status.kolyachaba.top` | Uptime Kuma |
| `vault.kolyachaba.top` | Vaultwarden |
| `temp.kolyachaba.top` | Shelly Temp Monitor |
| `portainer.kolyachaba.top` | Portainer |
| `gitlab.kolyachaba.top` | GitLab CE (LXC 103) |
| `traefik.kolyachaba.top` | Traefik dashboard |

**Full guide:** [GUIDE.md](GUIDE.md)

## Quick deploy

```bash
cd ~/homelab/traefik
cp .env.example .env          # edit ACME_EMAIL + CF_DNS_API_TOKEN
mkdir -p acme && touch acme/acme.json && chmod 600 acme/acme.json
docker network create frontend 2>/dev/null || true
docker compose up -d
```

## Verify

```bash
docker logs traefik -f
curl -I https://home.kolyachaba.top
```
