# Гайд: Traefik на homelab

Reverse proxy с автоматическим HTTPS для всех сервисов на `kolyachaba.top`.

---

## Что получится

```
Интернет
  ↓
Cloudflare DNS (*.kolyachaba.top)
  ↓
Роутер :443 → 192.168.178.194 (Traefik)
  ↓
Traefik (TLS Let's Encrypt via DNS)
  ├── home.kolyachaba.top      → Homepage
  ├── status.kolyachaba.top    → Uptime Kuma
  ├── vault.kolyachaba.top     → Vaultwarden
  ├── temp.kolyachaba.top      → Shelly Monitor
  ├── portainer.kolyachaba.top → Portainer
  ├── gitlab.kolyachaba.top    → GitLab (192.168.178.122)
  └── traefik.kolyachaba.top   → Dashboard
```

**Плюсы DNS challenge:**
- Не нужен открытый порт 80 для ACME HTTP challenge
- Работает за NAT
- Wildcard сертификат возможен

---

## Шаг 0: Что нужно заранее

- [ ] Домен `kolyachaba.top` в Cloudflare
- [ ] Docker LXC `192.168.178.194` с сетью `frontend`
- [ ] Все контейнеры в сети `frontend` (homepage, uptime-kuma, …)
- [ ] Проброс портов **80 и 443** на роутере → `192.168.178.194`

> **GitLab** на другом LXC — Traefik проксирует на `192.168.178.122:80` по IP.

---

## Шаг 1: Cloudflare API Token

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → **My Profile** → **API Tokens**
2. **Create Token** → шаблон **Edit zone DNS**
3. Zone: `kolyachaba.top`
4. Permissions: **Zone → DNS → Edit**
5. Скопируй token — он больше не покажется

---

## Шаг 2: DNS записи в Cloudflare

Для каждого поддомена — **A record** на твой **публичный IP**:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `home` | твой.public.ip | **DNS only** (серое облако) |
| A | `status` | твой.public.ip | DNS only |
| A | `vault` | твой.public.ip | DNS only |
| A | `temp` | твой.public.ip | DNS only |
| A | `portainer` | твой.public.ip | DNS only |
| A | `gitlab` | твой.public.ip | DNS only |
| A | `traefik` | твой.public.ip | DNS only |

**Почему DNS only (серое облако)?**
- GitLab, Portainer, WebSocket (Uptime Kuma) часто ломаются через оранжевое облако
- Traefik сам выдаёт TLS

**Узнать публичный IP:**
```bash
curl ifconfig.me
```

---

## Шаг 3: Проброс портов на роутере

| External | Internal | Device |
|----------|----------|--------|
| 80 | 192.168.178.194:80 | Traefik |
| 443 | 192.168.178.194:443 | Traefik |

Без этого снаружи не зайдёшь. LAN (`192.168.178.x`) работает и без проброса.

---

## Шаг 4: Подключи контейнеры к сети `frontend`

Traefik видит сервисы **по имени контейнера** в одной Docker-сети.

```bash
# Проверка
docker network inspect frontend --format '{{range .Containers}}{{.Name}} {{end}}'
```

Должны быть: `homepage`, `uptime-kuma`, `vaultwarden`, `shelly-temp-monitor`, `portainer`, `traefik`.

**Если portainer/lampac не в frontend:**
```bash
cd ~/homelab/portainer && docker compose up -d
cd ~/homelab/homepage && docker compose up -d
# и т.д.
```

**Lampac** у тебя в отдельной сети `/root/lampac` — Traefik до него не достучится, пока не добавишь роут вручную или не перенесёшь в `frontend`.

---

## Шаг 5: Deploy Traefik

На LXC 100:

```bash
cd ~/homelab
git pull origin main

cd traefik
cp .env.example .env
nano .env
```

Заполни `.env`:
```env
CF_DNS_API_TOKEN=твой_токен
ACME_EMAIL=твой@email.com
```

Отредактируй email в `traefik.yml` (строка `email:` под `acme`).

```bash
mkdir -p acme
touch acme/acme.json
chmod 600 acme/acme.json

docker compose up -d
docker logs traefik -f
```

**Успех:** в логах `Certificate obtained for domain home.kolyachaba.top` (может занять 1–2 мин).

---

## Шаг 6: Проверка

```bash
# Локально
curl -I http://192.168.178.194
# → 301 redirect на https

# Снаружи или с телефона (не WiFi)
curl -I https://home.kolyachaba.top
```

Открой в браузере:
- https://home.kolyachaba.top
- https://status.kolyachaba.top
- https://temp.kolyachaba.top

---

## Шаг 7: Обнови сервисы под новые URL

### Homepage `settings.yaml`
```yaml
# homepage/config/settings.yaml — добавь домены в allowed hosts
```

### Vaultwarden `.env`
```env
DOMAIN=https://vault.kolyachaba.top
```

### GitLab (LXC 103)
```bash
nano /etc/gitlab/gitlab.rb
```
```ruby
external_url 'https://gitlab.kolyachaba.top'
nginx['listen_port'] = 80
nginx['listen_https'] = false
```
```bash
gitlab-ctl reconfigure
```

GitLab за Traefik — HTTP внутри, HTTPS снаружи.

### Shelly app URL
```
https://temp.kolyachaba.top/webhook?temp={{temperature}}&device=bedroom
```

---

## Как это работает (для собеса)

| Файл | Роль |
|------|------|
| `traefik.yml` | Статика: entrypoints, ACME, providers |
| `dynamic/services.yml` | Роуты: Host → backend URL |
| `docker-compose.yaml` | Контейнер Traefik, порты 80/443 |
| `.env` | Cloudflare token (секрет) |

```
Запрос home.kolyachaba.top:443
  → Traefik entrypoint websecure
  → router "homepage" (rule Host)
  → TLS сертификат от Let's Encrypt (DNS challenge)
  → service homepage → http://homepage:3000
```

---

## Troubleshooting

### `client version 1.24 is too old` (Docker API)
- Новый Docker требует API 1.40+
- **Fix:** docker provider убран — роуты только через `dynamic/services.yml` (file provider)
- Перезапуск: `docker compose up -d --force-recreate`

### `unable to obtain ACME certificate`
- Проверь `CF_DNS_API_TOKEN` — права DNS Edit
- Email в `traefik.yml` должен быть валидным
- `chmod 600 acme/acme.json`

### `502 Bad Gateway`
- Контейнер не в сети `frontend`: `docker network connect frontend homepage`
- Неверное имя в `services.yml` — должно совпадать с `container_name`

### GitLab redirect loop
- `external_url` = https, но GitLab слушает HTTP — см. шаг 7

### Uptime Kuma websocket
- Обычно работает из коробки
- Если нет — добавь header middleware (редко нужно)

### Сертификат есть, снаружи не открывается
- Проброс 443 на роутере
- DNS A-record → правильный public IP
- Firewall Proxmox/LXC

---

## Безопасность (после базового setup)

1. **Dashboard** — `traefik.kolyachaba.top` лучше закрыть или добавить Basic Auth
2. **Portainer** — смени пароль, не свети публично без нужды
3. **`.env`** — только на сервере, в git через `.env.example`

---

## Добавить новый сервис

1. Контейнер в сеть `frontend`
2. DNS A-record в Cloudflare
3. В `dynamic/services.yml`:

```yaml
    myservice:
      rule: "Host(`myservice.kolyachaba.top`)"
      entryPoints: [websecure]
      service: myservice
      tls:
        certResolver: cloudflare

  services:
    myservice:
      loadBalancer:
        servers:
          - url: "http://container-name:PORT"
```

4. Traefik подхватит автоматически (`watch: true`)

---

## Roadmap после Traefik

- [ ] Убрать прямой доступ по `:3000`, `:8081` (опционально)
- [ ] Authentik SSO перед сервисами (как у Liviu)
- [ ] Prometheus metrics от Traefik
- [ ] Отключить Cloudflare Tunnel (LXC 102) если не нужен

---

## Полезные команды

```bash
docker logs traefik -f
docker exec traefik traefik healthcheck
docker network inspect frontend
curl -v https://home.kolyachaba.top 2>&1 | grep subject
```

**Конфиги в репо:** `homelab/traefik/` → push на GitHub после изменений.
