# LinkedIn EasyApply Anti-Detection Bot v2.0

> 🔬 Automated LinkedIn Easy Apply bot with advanced anti-detection bypass, reverse-engineered browser stealth, and AI-powered form filling — **for ethical hacking education and security research only**

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://python.org)
[![mypy strict](https://img.shields.io/badge/mypy-strict-green.svg)](https://mypy-lang.org)
[![ruff](https://img.shields.io/badge/linting-ruff-orange.svg)](https://docs.astral.sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

## ⚠️ Disclaimer

This project is strictly for **educational purposes** in the fields of ethical hacking, reverse engineering, and web automation security research. Using bots on LinkedIn violates their Terms of Service and may result in account restrictions or suspension. Use at your own risk. Consider using a secondary account for testing.

---

## 🔬 Research Focus

This project demonstrates practical exploitation of web application anti-bot defenses through:

- **Reverse engineering** of LinkedIn's bot detection mechanisms
- **Browser fingerprint spoofing** to evade automated detection systems
- **DOM trap evasion** and modal interception techniques
- **Stealth JavaScript injection** to bypass runtime integrity checks
- **AI-driven behavioral mimicry** using LLM-powered form interaction

---

## ✨ Features

### Core Automation

- **Playwright browser automation** with advanced anti-detection (stealth scripts, human-like delays)
- **DeepSeek AI integration** — answers form questions, calculates match scores, generates contextual responses
- **Smart filtering** — blacklists by title/company, minimum AI match score threshold
- **Multi-keyword search** — iterates through multiple keywords and locations with pagination
- **Session persistence** — cookies saved to avoid repeated authentication

### Resilience Engineering

- **Circuit Breaker** — protects against cascading API failures (CLOSED → OPEN → HALF_OPEN)
- **Exponential Backoff + Jitter** — intelligent retry for transient errors
- **Graceful Degradation** — aborts incompatible forms after `max_steps=10` without crashing
- **UI Trap Evasion** — detects and dismisses blocking modals ("Save/Discard application")

### Anti-Detection & Stealth

- External stealth JavaScript (`stealth.js`) injected into browser context
- Kernel-level click forcing (`force=True`) to bypass DOM traps
- Gaussian-distributed random delays (3–8 seconds)
- Human-like typing speed (30–120ms per character)
- `navigator.webdriver` flag hidden
- Fake browser plugins and language headers
- Real Chrome user-agent spoofing
- Cookie persistence (avoids repeated login detection)

### Code Quality

- **mypy --strict** — 0 errors across 16 source files
- **ruff** — 0 warnings (9 rules: E, F, W, I, N, UP, B, A, SIM)
- **Cyclomatic Complexity** — ≤7 average (radon)
- **100% type hints** — `ElementHandle`, `AsyncSession`, `SecretStr`
- **Custom exception hierarchy** — 15 specific error types
- **StrEnum** for state management — zero magic strings

### Python 3.14 Features

- **PEP 649** — Native deferred annotations (no `from __future__ import annotations`)
- **`datetime.UTC`** — Modern alias instead of `timezone.utc`
- **`AsyncGenerator[T]`** — Without redundant second `None` parameter
- **`zip(strict=True)`** — Length validation on paired iterations
- **Unquoted forward refs** — Clean type annotations (`DatabaseManager | None`)

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/LeandroPG19/linkedin-easyapply-antidetection-bot.git
cd linkedin-easyapply-antidetection-bot
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
DEEPSEEK_API_KEY=sk-your-key-here
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
RESUME_PATH=./resume.pdf
DRY_RUN=true  # Start with dry run!
```

Copy and edit the resume template:

```bash
cp resume.yaml.example resume.yaml
```

Edit `search_config.yaml` with your search preferences.

### 3. Run

```bash
# Dry run (does not submit applications)
python -m linkedin_bot.main

# Live mode (actually submits)
# Set DRY_RUN=false in .env first
python -m linkedin_bot.main

# Or use the registered CLI
linkedin-apply
```

---

## 📁 Architecture

```text
linkedin-easyapply-antidetection-bot/
├── linkedin_bot/
│   ├── __init__.py
│   ├── main.py            # Main orchestrator + CLI entry point
│   ├── config.py           # Pydantic Settings (.env) + SearchConfig (YAML)
│   ├── logger.py           # structlog (JSON structured logging)
│   ├── enums.py            # StrEnum: ApplicationStatus, CircuitState
│   ├── exceptions.py       # Hierarchy of 15 custom exceptions
│   ├── stealth.js          # Anti-detection JavaScript (injected into browser)
│   ├── ai_engine.py        # DeepSeek AI + Circuit Breaker + Retry
│   ├── browser.py          # Playwright session + stealth + human delays
│   ├── linkedin_auth.py    # Login + session verification
│   ├── job_search.py       # URL builder + listings extractor
│   ├── applicator.py       # Easy Apply form filler + multi-step navigation
│   ├── tracker.py          # Application tracking (dedup by job_id)
│   └── db/
│       ├── __init__.py
│       ├── models.py       # SQLAlchemy 2.0 models (ApplicationRecord)
│       ├── session.py      # DatabaseManager singleton (async SQLite)
│       └── repository.py   # Repository pattern (UPSERT + stats)
├── cookies/                # Saved sessions (gitignored)
├── logs/                   # bot_database.db + logs (gitignored)
├── resume.yaml.example     # Resume template (edit and rename to resume.yaml)
├── search_config.yaml      # Search filters
├── .env.example            # Credentials template
├── pyproject.toml          # Dependencies + ruff + mypy config
└── README.md
```

### Layer Diagram

```text
┌─────────────────────────────────────────┐
│            main.py (Orchestrator)       │
│  CLI → Config → Auth → Search → Apply  │
├─────────────────────────────────────────┤
│     ai_engine.py     │    tracker.py    │
│  Circuit Breaker     │  Deduplication   │
│  Retry + Backoff     │  Stats (by enum) │
├──────────────────────┼──────────────────┤
│     browser.py       │    db/           │
│  Playwright + Stealth│  SQLAlchemy 2.0  │
│  Human delays        │  Repository      │
│  Cookie persistence  │  DatabaseManager │
└──────────────────────┴──────────────────┘
```

---

## ⚙️ Configuration

### `.env` — Credentials & Behavior

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `DEEPSEEK_API_KEY` | DeepSeek API key | **Required** |
| `DEEPSEEK_BASE_URL` | API base URL | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | Model to use | `deepseek-chat` |
| `LINKEDIN_EMAIL` | LinkedIn email | **Required** |
| `LINKEDIN_PASSWORD` | LinkedIn password | **Required** |
| `RESUME_PATH` | Path to resume PDF | _(optional)_ |
| `MAX_APPLICATIONS_PER_SESSION` | Max apps per run | `30` |
| `MAX_PAGES_PER_SEARCH` | Max pages per keyword | `3` |
| `MIN_DELAY_SECONDS` | Minimum delay between actions | `3.0` |
| `MAX_DELAY_SECONDS` | Maximum delay between actions | `8.0` |
| `AI_MAX_RETRIES` | AI retries per call | `3` |
| `AI_RETRY_DELAY` | Base delay between retries | `2.0` |
| `DRY_RUN` | Test mode (no submissions) | `true` |
| `HEADLESS` | Headless browser | `false` |

### `search_config.yaml` — Job Search Filters

```yaml
keywords:
  - "Software Engineer"
  - "Backend Developer"
remote_only: true
experience_levels: [3, 4]    # 2=Entry, 3=Associate, 4=Mid-Senior
date_posted: 2               # 1=24h, 2=week, 3=month
locations: [""]               # Empty = no filter
blacklist_titles:
  - "senior"
  - "staff"
blacklist_companies:
  - "Acme Corp"
min_match_score: 50           # 0-100 (AI threshold)
```

### `resume.yaml` — Your Profile

See `resume.yaml.example` for a complete template with all supported fields.

---

## 🛡️ Resilience Patterns

| Pattern | Implementation |
| ------- | -------------- |
| **Circuit Breaker** | 5 consecutive failures → OPEN (30s cooldown) → HALF_OPEN (1 test) |
| **Exponential Backoff** | `delay = min(base × 2^attempt, max_delay)` + random jitter |
| **Deduplication** | Tracking by `job_id` (applied + dry_run + skipped) |
| **Graceful Abort** | Forms with >10 steps are aborted without crash |
| **Modal Evasion** | Auto-detects "Discard"/"Save" modals |
| **UPSERT** | If a `job_id` already exists in DB, updates status |

---

## 🔧 Development

### Code Verification

```bash
# Activate virtualenv
source .venv/bin/activate

# Linting (9 rules)
ruff check linkedin_bot/

# Type checking (strict mode)
mypy linkedin_bot/ --strict

# Cyclomatic complexity
radon cc linkedin_bot/ -a -nc

# All together
ruff check linkedin_bot/ && mypy linkedin_bot/ --strict && radon cc linkedin_bot/ -a -nc
```

### Dev Dependencies

```bash
pip install mypy types-PyYAML radon ruff
```

### Tech Stack

| Component | Technology | Version |
| --------- | ---------- | ------- |
| Runtime | Python | ≥3.14 |
| Browser | Playwright | ≥1.49.0 |
| AI | OpenAI SDK (DeepSeek) | ≥1.58.0 |
| ORM | SQLAlchemy (async) | ≥2.0.30 |
| DB | SQLite (aiosqlite) | ≥0.20.0 |
| Config | Pydantic Settings | ≥2.7.0 |
| Logging | structlog | ≥25.1.0 |
| HTTP | httpx | ≥0.28.0 |
| CLI | Rich | ≥13.9.0 |
| YAML | PyYAML | ≥6.0.2 |

---

## 💰 Cost

DeepSeek API is extremely affordable:

- ~50 applications/day × ~3 API calls = 150 calls
- **~$0.03 USD/day**

---

## 🔒 Security Notes

- **No credentials are stored in the repository** — all secrets via `.env` (gitignored)
- **No personal data in the codebase** — resume data via `resume.yaml` (gitignored)
- **Template files provided** — `.env.example` and `resume.yaml.example` with placeholder data
- **Anti-traversal protection** — all file paths resolved via `pathlib.resolve()`
- **SecretStr** — passwords never logged or serialized

---

## 📜 License

MIT — See [LICENSE](LICENSE) for details.
