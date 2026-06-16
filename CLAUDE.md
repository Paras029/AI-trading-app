# Apex Trading Bot — Architecture & Change Log

## What the App Does

Self-evolving, episode-based AI trading bot that runs paper simulations on real live prices.
- Paper trades BTC/ETH (crypto), AAPL/NVDA/SPY (US stocks), NIFTY/RELIANCE (India), EUR/USD + USD/INR (forex)
- Organises trading into **episodes**: start at $100, aim for $500 (5×). After each episode ends (goal hit or blowup) Claude reviews all trades, writes lessons, promotes/retires strategies, and opens the next generation with updated parameters.
- UI: 9 pages (Overview, Positions, Episodes, Evolution, Strategies, World, Lessons, Trades, Settings)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12 + FastAPI (async) |
| Frontend | React 18 + TypeScript + Tailwind CSS + Vite (port 3002) |
| Charts | TradingView `lightweight-charts` v4 |
| Database | PostgreSQL 16 |
| Cache / Pub-Sub | Redis 7 |
| AI (primary) | Anthropic Claude via `anthropic` SDK |
| AI (free tier) | Google Gemini via REST API (`httpx`) |
| Market data | ccxt (Binance crypto), Alpaca (US stocks), Kite (India), OANDA (forex) |
| Indicators | `pandas-ta` — RSI, MACD, Bollinger Bands, EMA20/50, ADX |
| Containers | Docker + Docker Compose |

---

## Directory Structure

```
/
├── docker-compose.yml
├── .env.example             ← copy to .env and fill in API keys
├── CLAUDE.md                ← this file
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                      # FastAPI factory + lifespan + router registration
│       ├── config.py                    # pydantic-settings + model list + prompt depth presets
│       ├── db/
│       │   ├── session.py               # async SQLAlchemy engine + get_db dependency
│       │   └── models/
│       │       ├── episode.py           # Episode (start_equity, goal, outcome, generation)
│       │       ├── trade.py             # Trade fills (entry/exit price, PnL, reason)
│       │       ├── position.py          # Open positions (mark price, SL/TP levels)
│       │       ├── signal.py            # AISignal (action, confidence, reasoning, indicators snapshot)
│       │       ├── strategy.py          # Strategy (stats gates, active/candidate/retired)
│       │       ├── lesson.py            # Lessons banked by Claude after each episode
│       │       ├── generation.py        # Gen N summaries (evolution log)
│       │       ├── knowledge.py         # Knowledge base entries (seeded + AI-written)
│       │       └── api_usage.py         # Token usage + cost per API call
│       ├── routers/
│       │   ├── ws.py                    # WebSocket /ws — live price + event broadcast
│       │   ├── overview.py              # GET /api/overview
│       │   ├── positions.py             # GET /api/positions
│       │   ├── episodes.py              # GET /api/episodes
│       │   ├── evolution.py             # GET /api/evolution (generations)
│       │   ├── strategies.py            # GET /api/strategies
│       │   ├── world.py                 # GET /api/world (macro context)
│       │   ├── lessons.py               # GET /api/lessons
│       │   ├── trades.py                # GET /api/trades
│       │   └── settings.py              # GET/PUT /api/settings, GET /api/costs
│       ├── services/
│       │   ├── market_data/
│       │   │   ├── ccxt_ws.py           # Binance OHLCV WebSocket → Redis
│       │   │   ├── alpaca_feed.py       # Alpaca US stocks data
│       │   │   ├── kite_feed.py         # Zerodha Kite India stocks data
│       │   │   └── world_feed.py        # Fear&Greed, headlines, macro, social
│       │   ├── indicators/
│       │   │   └── engine.py            # pandas-ta indicators + should_call_llm() pre-filter
│       │   ├── ai/
│       │   │   ├── signal_generator.py  # Multi-provider: Claude + Gemini → BUY/SELL/HOLD
│       │   │   ├── episode_reviewer.py  # Claude post-episode analysis → lessons + gen summary
│       │   │   └── prompt_builder.py    # Prompt assembly with depth presets
│       │   ├── execution/
│       │   │   ├── paper.py             # Paper broker (fills at mark price + 0.05% slippage)
│       │   │   └── ccxt_broker.py       # Live broker (opt-in, set TRADING_MODE=live)
│       │   ├── strategy_engine.py       # Stats gates → promote/retire strategies
│       │   ├── risk.py                  # Kelly sizing, SL/TP levels, liquidation watch
│       │   ├── episode_manager.py       # Episode open/close, triggers evolution
│       │   ├── pipeline.py              # Two-loop orchestrator: fast SL + slow signals
│       │   ├── cost_tracker.py          # track_usage() — persists token cost to DB
│       │   └── knowledge_seeder.py      # Seeds 12 foundational knowledge entries at startup
│       ├── core/
│       │   ├── redis_client.py          # aioredis pool + pub/sub + get/set_bot_config()
│       │   └── websocket_manager.py     # Broadcasts Redis events → all WS clients
│       └── tasks/
│           └── runner.py                # Starts all background asyncio tasks
└── frontend/
    ├── public/
    │   ├── manifest.json                # PWA manifest (Android install)
    │   └── sw.js                        # Service worker (offline shell caching)
    ├── index.html                       # Entry point + PWA meta tags + SW registration
    └── src/
        ├── App.tsx                      # Routes: 9 pages including /settings
        ├── store/index.ts               # Zustand: market, episode, signals, portfolio
        ├── hooks/useWebSocket.ts        # WS → Zustand live updates
        └── components/
            ├── layout/
            │   ├── Layout.tsx
            │   └── Sidebar.tsx          # Nav + CostWidget + market selector
            ├── settings/
            │   ├── SettingsPage.tsx     # Model picker + depth picker + cost breakdown
            │   └── CostWidget.tsx       # Sidebar cost chip (today $ + model name)
            ├── overview/OverviewPage.tsx
            ├── positions/PositionsPage.tsx
            ├── episodes/EpisodesPage.tsx
            ├── evolution/EvolutionPage.tsx
            ├── strategies/StrategiesPage.tsx
            ├── world/WorldPage.tsx
            ├── lessons/LessonsPage.tsx
            └── trades/TradesPage.tsx
```

---

## Data Flow

```
Binance WebSocket → Redis "candles:BTCUSDT:1m" + pub "ticks:BTCUSDT"
                                    ↓
Indicator Engine (on each candle) → Redis "indicators:BTCUSDT"
                                    ↓
should_call_llm() — Layer 1 pre-filter (zero tokens if market is flat)
                                    ↓ (only if actionable setup detected)
Signal Generator → Claude or Gemini → {action, confidence, reasoning, risk_note}
                                    ↓
Risk Manager (Kelly sizing) → approve or veto
                                    ↓
Paper Broker → fill at mark price → Trade + Position in PostgreSQL
                                    ↓
Episode Manager → checks equity vs goal/blowup floor
                                    ↓ (on episode end)
Episode Reviewer (Claude Sonnet) → lessons + generation summary
Strategy Engine → promote/retire → next episode with updated params
                                    ↓
WebSocket → all connected browser clients → live UI update
```

---

## Two-Loop Pipeline (pipeline.py)

The trading pipeline runs two independent async loops per market:

| Loop | Interval | What it does |
|---|---|---|
| `run_sl_monitor(market)` | Every 10s | Checks SL/TP on all open positions. No AI calls. Fast. |
| `run_signal_loop(market)` | Every 60s | Processes all symbols in parallel via `asyncio.gather()`. Calls AI for each that passes the pre-filter. |

### Layer 1: Indicator Pre-filter (`should_call_llm()`)
Returns `True` (call AI) only when any of these fire:
- RSI < 30 or RSI > 70
- MACD histogram crossed zero (sign change)
- Price at or beyond a Bollinger Band (±0.1%)
- ADX > 25 AND price well beyond both EMAs (strong trend breakout)

Eliminates ~75% of AI calls.

---

## AI Models

All models are defined in `backend/app/config.py → AVAILABLE_SIGNAL_MODELS`. Only models in this list appear in the Settings page dropdown. Never hardcode in the frontend.

| Model | Provider | Cost | Use case |
|---|---|---|---|
| `gemini-2.0-flash` | Google | **Free** (1500 req/day) | Best starting point — zero cost |
| `gemini-1.5-flash` | Google | **Free** (1500 req/day) | Reliable fallback |
| `claude-haiku-4-5-20251001` | Anthropic | ~$0.80/$4 per M tokens | Fast & cheap paid option |
| `claude-sonnet-4-6` | Anthropic | ~$3/$15 per M tokens | Best quality, episode reviews always use this |

Episode reviews always use `settings.claude_model` (Sonnet) regardless of the UI setting — they're infrequent and quality matters.

### Adding a new model
1. Add entry to `AVAILABLE_SIGNAL_MODELS` in `backend/app/config.py`
2. If it's a new provider, add a `_call_<provider>()` function in `signal_generator.py`
3. Add pricing to `_PRICING` in `cost_tracker.py` (or it defaults to Sonnet pricing)
4. Restart the backend — the frontend picks it up automatically from `/api/settings`

---

## Runtime Config (Redis)

Stored in `Redis → "bot:config"`. Editable live via the Settings page — no restart needed.

| Key | Default | Description |
|---|---|---|
| `signal_model` | `claude-sonnet-4-6` | Model used for trade signals |
| `prompt_depth` | `standard` | How much context to send per prompt |

### Prompt Depth Presets

| Depth | Candles | Headlines | Knowledge | Max tokens | Use case |
|---|---|---|---|---|---|
| compact | 3 | 2 | 1 | 300 | Minimum cost, fast decisions |
| standard | 5 | 3 | 2 | 400 | Balanced (default) |
| rich | 10 | 5 | 5 | 600 | Most context, highest quality |

---

## API Keys Required

Copy `.env.example` → `.env` and fill in:

| Key | Required for | Where to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude signals + episode reviews | console.anthropic.com |
| `GOOGLE_API_KEY` | Gemini signals (free) | aistudio.google.com/app/apikey |
| `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | US stocks data | alpaca.markets |
| `BINANCE_API_KEY` + `BINANCE_SECRET` | Crypto live trading (not needed for data) | binance.com |
| `KITE_API_KEY` etc. | India stocks | kite.zerodha.com |
| `OANDA_API_KEY` + `OANDA_ACCOUNT_ID` | Forex | oanda.com |

Minimum to get started: **ANTHROPIC_API_KEY** or **GOOGLE_API_KEY** (the rest are optional for paper mode).

---

## Android / Mobile (PWA)

The app is a Progressive Web App. To install on Android:
1. Start the app (`docker-compose up`)
2. Open `http://<your-server-ip>:3002` in Chrome on Android
3. Tap the menu → "Add to Home Screen"
4. The app installs and opens fullscreen like a native app

For remote access from Android while the server runs at home: use [Tailscale](https://tailscale.com/) (free) or `ngrok` to tunnel port 3002.

PWA files:
- `frontend/public/manifest.json` — app name, icons, theme colour
- `frontend/public/sw.js` — service worker (caches app shell for offline loading)
- `frontend/index.html` — registers the SW and links the manifest

---

## Running Locally

```bash
cp .env.example .env
# Edit .env — add at least ANTHROPIC_API_KEY or GOOGLE_API_KEY

docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3002
# API docs: http://localhost:8000/docs
```

---

## Switching to Live Trading

1. Set `TRADING_MODE=live` in `.env`
2. Fill in real broker API keys (Binance, Alpaca, Kite, OANDA)
3. The broker layer in `services/execution/` dispatches to `ccxt_broker.py` when `TRADING_MODE=live`
4. Start with a small test amount. The Kelly fraction and stop-losses are designed to limit drawdown.

---

## Cost Tracking

Every API call is logged to the `api_usage` table:
- model, call_type (signal/episode_review), market, episode_id
- input_tokens, output_tokens, cache_read_tokens, cost_usd

View costs live at: `GET /api/costs?period=today|week|all`

Also visible in the Settings page → "API Cost" section, and in the sidebar CostWidget.

---

## Phase History

| Phase | What was built |
|---|---|
| Phase 1 | Full app scaffold: Docker, DB models (7 tables), market data feeds (crypto/US/India/forex), indicators, world feed, signal generator, paper broker, risk manager, episode manager, episode reviewer, strategy engine, all 8 REST routers, WebSocket, 8 frontend pages, Zustand store, knowledge seeder (12 entries) |
| Phase 2 | Speed + token efficiency: split pipeline into fast SL loop (10s) + slow signal loop (60s) with `asyncio.gather()`; added `should_call_llm()` indicator pre-filter (saves ~75% AI calls); compact prompts with depth presets |
| Phase 3 | UI config + cost tracking: model selector in Settings UI; prompt depth radio cards; live API cost display (sidebar widget + full breakdown page); `ApiUsage` DB table; `track_usage()` service; `/api/settings` + `/api/costs` endpoints |
| Phase 4 | Multi-provider AI: added Google Gemini (2.0 Flash, 1.5 Flash) as free alternatives via REST API; PWA support for Android (manifest + service worker) |
