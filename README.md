# LinkedIn Auto-Apply Bot v2.0

> 🤖 Bot de automatización de LinkedIn Easy Apply con IA DeepSeek, browser stealth y resiliencia industrial

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://python.org)
[![mypy strict](https://img.shields.io/badge/mypy-strict-green.svg)](https://mypy-lang.org)
[![ruff](https://img.shields.io/badge/linting-ruff-orange.svg)](https://docs.astral.sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

## ✨ Características

### Core
- **Playwright browser automation** con anti-detección avanzada (stealth scripts, delays humanos)
- **DeepSeek AI integration** — responde preguntas de formulario, calcula match scores, genera cover letters
- **Smart filtering** — blacklists por título/empresa, umbral mínimo de match score
- **Multi-keyword search** — itera por múltiples palabras clave y ubicaciones
- **Session persistence** — cookies guardadas para evitar re-login

### Resiliencia
- **Circuit Breaker** — protege contra API failures con patrón CLOSED → OPEN → HALF_OPEN
- **Exponential Backoff + Jitter** — reintentos inteligentes para errores transitorios
- **Graceful Degradation** — aborta formularios incompatibles después de `max_steps=10` sin crashear
- **UI Trap Evasion** — detecta y descarta modales de bloqueo agresivos ("Save/Discard application")

### Anti-Detección
- Stealth JavaScript externo (`stealth.js`) inyectado al navegador
- Kernel-level click forcing (`force=True`) para bypass de trampas DOM
- Delays aleatorios (distribución gaussiana, 3-8 segundos)
- Velocidad de tipeo humana (30-120ms por carácter)
- Flag `navigator.webdriver` oculto
- Plugins y lenguajes de navegador falsos
- User-agent de Chrome real
- Cookie persistence (evita logins repetidos)

### Calidad de Código
- **mypy --strict** — 0 errores propios en 16 archivos
- **ruff** — 0 warnings (9 reglas activas: E, F, W, I, N, UP, B, A, SIM)
- **Complejidad Ciclomática** — ≤7 promedio (radon)
- **100% type hints** — `ElementHandle`, `AsyncSession`, `SecretStr`
- **Custom exception hierarchy** — 15 tipos de error específicos
- **StrEnum** para estados — cero magic strings

### Python 3.14 Features
- **PEP 649** — Deferred annotations nativas (sin `from __future__ import annotations`)
- **`datetime.UTC`** — Alias moderno en vez de `timezone.utc`
- **`AsyncGenerator[T]`** — Sin segundo parámetro `None` redundante
- **`zip(strict=True)`** — Validación de longitud en iteraciones pareadas
- **Forward refs sin comillas** — Anotaciones de tipo sin strings (`DatabaseManager | None`)

---

## 🚀 Quick Start

### 1. Clonar e instalar

```bash
git clone <repo-url> && cd linkedin-auto-apply
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

### 2. Configurar

```bash
cp .env.example .env
```

Editar `.env` con tus credenciales:

```env
DEEPSEEK_API_KEY=sk-your-key-here
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
RESUME_PATH=./resume.pdf
DRY_RUN=true  # ¡Empieza con dry run!
```

Editar `resume.yaml` con tu información real.

Editar `search_config.yaml` con tus preferencias de búsqueda.

### 3. Ejecutar

```bash
# Dry run (no envía aplicaciones)
python -m linkedin_bot.main

# Modo live (envía de verdad)
# Cambia DRY_RUN=false en .env primero
python -m linkedin_bot.main

# O usa el CLI registrado
linkedin-apply
```

---

## 📁 Arquitectura

```
linkedin-auto-apply/
├── linkedin_bot/
│   ├── __init__.py
│   ├── main.py            # Orquestador principal + CLI entry point
│   ├── config.py           # Pydantic Settings (.env) + SearchConfig (YAML)
│   ├── logger.py           # structlog (JSON structured logging)
│   ├── enums.py            # StrEnum: ApplicationStatus, CircuitState
│   ├── exceptions.py       # Jerarquía de 15 excepciones custom
│   ├── stealth.js          # Anti-detección JavaScript (inyectado al browser)
│   ├── ai_engine.py        # DeepSeek AI + Circuit Breaker + Retry
│   ├── browser.py          # Playwright session + stealth + human delays
│   ├── linkedin_auth.py    # Login + verificación de sesión
│   ├── job_search.py       # URL builder + extractor de listings
│   ├── applicator.py       # Easy Apply form filler + multi-step nav
│   ├── tracker.py          # Application tracking (dedup por job_id)
│   └── db/
│       ├── __init__.py
│       ├── models.py       # SQLAlchemy 2.0 models (ApplicationRecord)
│       ├── session.py      # DatabaseManager singleton (async SQLite)
│       └── repository.py   # Repository pattern (UPSERT + stats)
├── cookies/                # Sesiones guardadas (gitignored)
├── logs/                   # bot_database.db + logs (gitignored)
├── resume.yaml             # Tu CV estructurado
├── resume.pdf              # Tu CV en PDF (para upload)
├── search_config.yaml      # Filtros de búsqueda
├── .env                    # Credenciales (gitignored)
├── .env.example            # Template
├── pyproject.toml          # Dependencias + ruff + mypy config
└── README.md
```

### Capas

```
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

## ⚙️ Configuración

### `.env` — Credenciales y comportamiento

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | API key de DeepSeek | **Requerido** |
| `DEEPSEEK_BASE_URL` | URL base de la API | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | Modelo a usar | `deepseek-chat` |
| `LINKEDIN_EMAIL` | Email de LinkedIn | **Requerido** |
| `LINKEDIN_PASSWORD` | Contraseña de LinkedIn | **Requerido** |
| `RESUME_PATH` | Ruta al PDF del CV | _(opcional)_ |
| `MAX_APPLICATIONS_PER_SESSION` | Máx. apps por ejecución | `30` |
| `MAX_PAGES_PER_SEARCH` | Máx. páginas por keyword | `3` |
| `MIN_DELAY_SECONDS` | Delay mínimo entre acciones | `3.0` |
| `MAX_DELAY_SECONDS` | Delay máximo entre acciones | `8.0` |
| `AI_MAX_RETRIES` | Reintentos de AI por llamada | `3` |
| `AI_RETRY_DELAY` | Delay base entre reintentos | `2.0` |
| `DRY_RUN` | Modo test (no envía) | `true` |
| `HEADLESS` | Navegador sin ventana | `false` |

### `search_config.yaml` — Búsqueda de empleos

```yaml
keywords:
  - "Software Engineer"
  - "Backend Developer"
remote_only: true
experience_levels: [3, 4]    # 2=Entry, 3=Associate, 4=Mid-Senior
date_posted: 2               # 1=24h, 2=semana, 3=mes
locations: [""]               # Vacío = sin filtro
blacklist_titles:
  - "senior"
  - "staff"
blacklist_companies:
  - "Acme Corp"
min_match_score: 50           # 0-100 (umbral de IA)
```

### `resume.yaml` — Tu perfil

```yaml
personal:
  name: "Tu Nombre"
  location: "Ciudad, País"
  email: "tu@email.com"
summary: "Resumen profesional..."
skills:
  languages: ["Python", "TypeScript"]
  frameworks: ["FastAPI", "React"]
experience:
  - company: "Empresa"
    role: "Puesto"
    duration: "2020-2024"
    highlights:
      - "Logro cuantificable"
default_answers:
  years_of_experience: "5"
  work_authorization: "yes"
  salary_expectation: "100000"
```

---

## 🛡️ Patrones de Resiliencia

| Patrón | Implementación |
|--------|---------------|
| **Circuit Breaker** | 5 fallos consecutivos → OPEN (30s cooldown) → HALF_OPEN (1 test) |
| **Exponential Backoff** | `delay = min(base × 2^attempt, max_delay)` + random jitter |
| **Deduplication** | Tracking por `job_id` (applied + dry_run + skipped) |
| **Graceful Abort** | Formularios con >10 pasos se abortan sin crash |
| **Modal Evasion** | Detecta "Discard"/"Save" modals automáticamente |
| **UPSERT** | Si un `job_id` ya existe en DB, actualiza status |

---

## 🔧 Desarrollo

### Verificación de código

```bash
# Activar virtualenv
source .venv/bin/activate

# Linting (9 reglas)
ruff check linkedin_bot/

# Type checking (strict mode)
mypy linkedin_bot/ --strict

# Complejidad ciclomática
radon cc linkedin_bot/ -a -nc

# Todo junto
ruff check linkedin_bot/ && mypy linkedin_bot/ --strict && radon cc linkedin_bot/ -a -nc
```

### Dependencias de desarrollo

```bash
pip install mypy types-PyYAML radon ruff
```

### Stack

| Componente | Tecnología | Versión |
|-----------|-----------|---------|
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

## 💰 Costo

DeepSeek API es extremadamente económico:

- ~50 aplicaciones/día × ~3 llamadas API = 150 llamadas
- **~$0.03 USD/día**

---

## ⚠️ Disclaimer

Esta herramienta es con **fines educativos**. Usar bots en LinkedIn viola sus
Términos de Servicio y puede resultar en restricciones o suspensión de cuenta.
Úsala bajo tu propio riesgo. Considera usar una cuenta secundaria para pruebas.
