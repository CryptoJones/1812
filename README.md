# 1812

**A self-hosted Discord chatbot with configurable LLM backends, persistent memory, and a FastAPI dashboard.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?logo=apache)](https://opensource.org/licenses/Apache-2.0)
[![GitHub](https://img.shields.io/badge/GitHub-CryptoJones%2F1812-181717?logo=github&logoColor=white)](https://github.com/CryptoJones/1812)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Discord](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Version](https://img.shields.io/badge/version-v0.2.0--dev-orange)]()

> *"Cannons firing. Bells ringing. The overture begins."*
> — Tchaikovsky, 1880

---

## Overview

1812 is a self-hosted, open-source Discord chatbot backed by your choice of LLM. It maintains
per-channel conversation history in SQLite, streams responses token-by-token, supports image input,
and ships with a FastAPI health/dashboard sidecar.

Named after Tchaikovsky's 1812 Overture — a piece that knows exactly when to be quiet
and exactly when to be deafening.

A **CryptoJones** project.

---

## Features

| Feature | Details |
|---|---|
| **Multi-backend LLM** | OpenAI, Anthropic Claude, Ollama (local), OpenRouter |
| **Streaming responses** | Token-by-token output, edited live in Discord |
| **SQLite persistence** | Per-channel history and per-server personas survive restarts |
| **Per-user memory** | Remember facts about individual users across sessions |
| **Per-server personas** | Different personality per Discord server |
| **Slash commands** | `/clear`, `/persona`, `/model`, `/remember`, `/forget` |
| **Image input** | Attach images — vision-capable models process them inline |
| **Rate limiting** | Per-user sliding window (configurable requests/window) |
| **Auto-summarisation** | History is summarised by the LLM when it gets too long |
| **FastAPI sidecar** | `/health`, `/api/channels`, `/api/history/:id`, and a live dashboard |
| **JSON structured logging** | Machine-readable logs with level, timestamp, and context |
| **Docker** | Single-container deploy via `docker-compose up` |
| **Graceful shutdown** | SIGTERM/SIGINT handled cleanly |

---

## Architecture

| Component | Technology |
|---|---|
| Bot framework | [discord.py](https://discordpy.readthedocs.io/) 2.3+ |
| LLM backends | OpenAI / Anthropic / Ollama / OpenRouter |
| History storage | SQLite via `aiosqlite` |
| Config | Pydantic Settings + `.env` |
| Web sidecar | FastAPI + uvicorn (background thread) |
| Container | Docker + Docker Compose |
| Tests | pytest + pytest-asyncio |

---

## Quick Start

**Docker (recommended)**
```bash
cp .env.example .env
# Edit .env with your tokens
docker compose up -d
```

**Manual**
```bash
chmod +x setup.sh && ./setup.sh
cp .env.example .env
# Edit .env with your tokens
source .venv/bin/activate
python bot.py
```

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Your Discord bot token |
| `LLM_PROVIDER` | No | `openai` | `openai` \| `anthropic` \| `ollama` \| `openrouter` |
| `LLM_MODEL` | No | `gpt-4o-mini` | Model name for the selected provider |
| `OPENAI_API_KEY` | If OpenAI | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | If Anthropic | — | Anthropic API key |
| `OPENROUTER_API_KEY` | If OpenRouter | — | OpenRouter API key |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434/v1` | Ollama endpoint |
| `SYSTEM_PROMPT` | No | `You are 1812...` | Default bot personality |
| `MAX_HISTORY_MESSAGES` | No | `20` | Messages to keep per channel before summarising |
| `SUMMARISE_AT` | No | `40` | History length that triggers summarisation |
| `RATE_LIMIT_REQUESTS` | No | `10` | Max requests per user per window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Rate limit sliding window |
| `DB_PATH` | No | `1812.db` | Path to SQLite database file |
| `WEB_HOST` | No | `0.0.0.0` | FastAPI sidecar host |
| `WEB_PORT` | No | `8080` | FastAPI sidecar port |
| `SHUTDOWN_AFTER_MINUTES` | No | unset (= unbounded) | Auto-shutdown timer in minutes. CLI `--shutdown-after N` overrides this. |

---

## CLI Flags

| Flag | Description |
|---|---|
| `--shutdown-after N` | Self-shutdown after N minutes of runtime. Overrides `SHUTDOWN_AFTER_MINUTES`. `0` is an explicit "unbounded" sentinel that clears any env value. Useful for time-boxed runs, cron jobs, and CI canaries. |

```bash
# Run for exactly two hours, then graceful shutdown.
python bot.py --shutdown-after 120

# Wipe an env-configured timer for this invocation only.
SHUTDOWN_AFTER_MINUTES=30 python bot.py --shutdown-after 0
```

---

## Slash Commands

| Command | Who | Description |
|---|---|---|
| `/clear` | Anyone | Wipe conversation history for the current channel |
| `/persona <name>` | Anyone | Switch persona: `default`, `concise`, `creative`, `technical` |
| `/model <name>` | Admin only | Change the LLM model at runtime |
| `/remember <text>` | Anyone | Save a personal note about yourself for the bot to use |
| `/forget` | Anyone | Clear your personal memory |

---

## Discord Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create or select your application
3. Navigate to **Bot** → enable **Message Content Intent** and **Server Members Intent**
4. Copy your bot token into `.env`
5. Invite via **OAuth2 → URL Generator** — scopes: `bot`, `applications.commands` — permissions: `Send Messages`, `Read Message History`, `Attach Files`

---

## Web Dashboard

The FastAPI sidecar runs on port 8080 by default:

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /api/channels` | List all channels with history |
| `GET /api/history/{channel_id}` | Full message history for a channel |
| `GET /` | Live HTML dashboard |

---

## Project Structure

```
1812/
├── bot.py              # Discord bot, slash commands, streaming
├── config.py           # Pydantic Settings
├── db.py               # SQLite helpers (aiosqlite)
├── llm.py              # LLM backend abstraction (OpenAI / Anthropic / Ollama / OpenRouter)
├── rate_limiter.py     # Per-user sliding window rate limiter
├── web.py              # FastAPI sidecar
├── tests/              # pytest test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── setup.sh
└── .env.example
```

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

31 tests covering rate limiting, database operations, LLM backend selection, and bot helpers.

---

## Contributing

Pull requests welcome. Keep it simple. Keep it clean. Write tests first.

---

## License

**Apache License 2.0** — Copyright 2026 Aaron K. Clark. See [LICENSE](LICENSE).

---

## Acknowledgments

To **Dr. John Crichton** of the Farscape Project — astronaut, wormhole theorist, and the most
unlikely hero to ever fall through the wrong end of the universe. Wherever he is.

---

Proudly Made in Nebraska. 🌽
