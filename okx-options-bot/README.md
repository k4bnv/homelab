# okx-options-bot

Читает данные по опционам BTC/ETH на OKX каждые 15 минут и присылает дайджест
в Telegram: технические индикаторы базового актива, метрики опционного рынка
(IV, skew, put/call OI) и OI-взвешенные греки ближайшей экспирации.

Это **не торговый бот** — только чтение публичных/приватных read-only
эндпоинтов OKX v5 REST API. Ни один эндпоинт размещения ордеров нигде не
используется. Сигнал ("Bullish"/"Bearish"/"Neutral") — это простая
эвристика для привлечения внимания к заметным сетапам, а не финансовый
совет.

## Что анализируется

Раз в 15 минут (по циклу `POLL_INTERVAL_SECONDS`, по умолчанию 900с),
для каждого символа из `SYMBOLS`:

1. **Технический анализ базового актива** — свечи `{SYMBOL}-USDT` бар 15m
   (`/api/v5/market/candles`): RSI(14), MACD(12,26,9), EMA9/EMA21.
2. **Метрики опционного рынка** — сводка по опционам `{SYMBOL}-USD`
   (`/api/v5/public/opt-summary`) для ближайшей экспирации:
   - ATM implied volatility (средняя IV колла/пута у страйка, ближайшего к споту)
   - 25-delta skew (IV пута минус IV колла на дельте ~0.25/-0.25)
   - Put/Call open interest ratio и OI-взвешенные греки (Delta/Gamma/Theta/Vega),
     на основе `/api/v5/public/open-interest`
3. Результат объединяется в эвристический bias-скор и отправляется в Telegram.

## Настройка

```bash
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID (обязательно)
# OKX_API_KEY/SECRET/PASSPHRASE опциональны: без них бот использует
# публичные эндпоинты OKX без подписи запроса; с ключами запросы
# подписываются (HMAC-SHA256 по OKX v5 auth) для более высокого rate-limit.
docker compose up -d --build
```

Ключи OKX создаются в разделе API Management на okx.com. Для этого бота
достаточно **read-only** прав — права на торговлю/вывод включать не нужно.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OKX_BASE_URL` | `https://www.okx.com` | REST endpoint OKX |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_API_PASSPHRASE` | пусто | опционально, только read-only доступ |
| `SYMBOLS` | `BTC,ETH` | список базовых активов через запятую |
| `CANDLE_BAR` | `15m` | таймфрейм свечей |
| `CANDLE_LIMIT` | `150` | сколько свечей запрашивать для индикаторов |
| `POLL_INTERVAL_SECONDS` | `900` | интервал цикла анализа (15 мин) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | обязательны для отправки дайджеста |
| `LOG_LEVEL` | `INFO` | уровень логирования |

## Тесты

```bash
pip install -r requirements.txt
pytest
```

Тесты офлайн: сеть мокается через `respx`, реальные вызовы к OKX не
выполняются.

## Важно

Схема эндпоинтов OKX v5 (`/api/v5/market/candles`,
`/api/v5/public/opt-summary`, `/api/v5/public/open-interest`) реализована
по официальной документации OKX и может со временем меняться на их
стороне — перед продовым использованием стоит сверить актуальные поля
ответа с https://www.okx.com/docs-v5/en/.
