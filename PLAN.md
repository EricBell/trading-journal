# Plan: Merge CSV Parser + Flask Web App + Docker/Dokploy

## Context

Two goals:
1. **Merge `schwab-csv-to-json`** into this project so CSV files can be ingested directly — no separate pre-processing step.
2. **Build a Flask web app** so the journal is visual and browser-deployable — upload files, view charts, browse trades.

**Deployment target:** Dokploy VPS (Docker-based PaaS). Two Docker configurations: local desktop testing and Dokploy production.

**Recommended order: Merge CSV parser → Flask app → Docker**
The merge establishes the complete pipeline (CSV → parse → DB → process trades) that Flask routes build on top of. Docker wraps the finished Flask app.

**User decisions:**
- Multi-user (existing user isolation infrastructure applies)
- Web-primary; CLI kept only for admin/deployment operations
- UI: Bootstrap 5 + Chart.js

---

## Phase 1: Merge CSV Parser

### What moves into trading-journal

| Source (schwab-csv-to-json) | Destination (trading-journal) |
|---|---|
| `main.py` parsing functions | `trading_journal/csv_parser.py` |
| `batch.py` multi-file logic | folded into `csv_parser.py` |
| `patterns.json` | `trading_journal/data/patterns.json` |
| `tests/test_main.py`, `test_batch.py`, `test_integration.py`, `test_validation.py` | `tests/` (renamed/adapted) |

### What is NOT brought over

- `tui.py` — replaced entirely by the web UI
- Standalone `schwab-csv-to-json convert` CLI — replaced by web upload form
- All output-format options (`--output-json/ndjson`, `--pretty`) — output is the DB, not files
- `--preview N`, `--max-rows N` — dev/testing scaffolding
- `--force-overwrite` — irrelevant (no output file)
- `--qty-unsigned/--qty-signed` — fixed policy: always signed
- `--skip-empty-sections/--include-empty-sections` — fixed policy: skip
- `--group-by-section/--preserve-file-order` — fixed policy: group and sort by time
- `--filter-triggered-rejected/--include-all-statuses` — fixed policy: filter
- `--section-patterns-file` — loaded from bundled `patterns.json`; not user-configurable
- schwab-csv-to-json's own version files, standalone CLI scripts

### New module: `trading_journal/csv_parser.py`

Public API:

```python
class CsvParser:
    def __init__(self, include_rolling: bool = False, encoding: str = 'utf-8'): ...
    def parse_file(self, file_path: str) -> List[dict]: ...
    def parse_files(self, file_paths: List[str]) -> List[dict]: ...
```

Internal helpers migrated verbatim from `schwab-csv-to-json/main.py` and `batch.py`:
`detect_section_from_row`, `compile_section_patterns`, `map_header_to_index`, `normalize_key`,
`safe_get`, `classify_row`, `build_order_record`, `parse_integer_qty`, `parse_float_field`,
`parse_datetime_maybe`, `parse_exp_date`, `group_and_sort_records`

`patterns.json` loaded via `importlib.resources` from `trading_journal/data/`.

### Updated ingestion pipeline

**Before:** CSV → schwab-csv-to-json (external) → NDJSON file → `NdjsonIngester` → DB
**After:** CSV → `CsvParser` → `List[dict]` → `NdjsonIngester.ingest_records()` → DB

Modify `NdjsonIngester` to add:
```python
def ingest_records(self, records: List[dict], dry_run: bool = False) -> IngestResult
```
Existing `ingest_file()` stays for backward compat (used by admin CLI).

### CLI changes in Phase 1

**Add:** `trading-journal ingest csv <file.csv> [<file2.csv>...]`
Admin/emergency tool for direct CSV import.
Options kept: `--include-rolling`, `--encoding`, `--dry-run`, `--verbose`

**Remove from CLI:**
- `ingest file` and `ingest batch` (primary path shifts to web upload)
- `env` command — only useful for exporting shell API key vars
- `--profile` global option — not meaningful in single-server web deployment

### Files modified (Phase 1)
- `trading_journal/csv_parser.py` — new
- `trading_journal/data/patterns.json` — new
- `trading_journal/data/__init__.py` — new (empty package marker)
- `trading_journal/ingestion.py` — add `ingest_records()` method
- `trading_journal/cli.py` — add `ingest csv`; remove `env`, `ingest file/batch`, `--profile`
- `pyproject.toml` — add package-data config; version bump to `0.5.0`
- `tests/test_csv_parser.py` — new (adapted from schwab-csv-to-json test suite)

---

## Phase 2: Flask Web App

### New entry point: `wsgi.py`

```python
from trading_journal.web import create_app
app = create_app()
```

`main.py` remains as the CLI entry point.

### Package structure

```
trading_journal/
  web/
    __init__.py              # create_app() factory, Blueprint registration
    auth.py                  # SessionAuthProvider + @login_required + @admin_required
    routes/
      __init__.py
      auth.py                # GET/POST /login, POST /logout
      dashboard.py           # GET /
      trades.py              # GET /trades, GET /trades/<id>, POST /trades/<id>/annotate
      positions.py           # GET /positions
      ingest.py              # GET/POST /upload
      admin.py               # GET /admin/users, POST /admin/users/create, etc.
      api.py                 # GET /api/dashboard, GET /api/trades (JSON for Chart.js)
    templates/
      base.html              # Bootstrap 5 navbar, flash messages, Chart.js CDN
      auth/login.html
      dashboard/index.html   # Charts + KPI cards
      trades/index.html      # Filterable table
      trades/detail.html     # Executions, notes editor, pattern selector
      positions/index.html
      ingest/upload.html     # Multi-file drag-and-drop
      ingest/result.html     # Import summary
      admin/users.html
    static/
      css/custom.css
      js/charts.js           # Chart.js initialization helpers
```

### Routes

| Route | Methods | Auth | Description |
|---|---|---|---|
| `/login` | GET, POST | public | Session login |
| `/logout` | POST | any | Clear session |
| `/` | GET | required | Dashboard with 4 Chart.js charts + KPI cards |
| `/trades` | GET | required | Trades table; `?symbol=`, `?range=7d` query params |
| `/trades/<id>` | GET | required | Trade detail: executions, notes, pattern |
| `/trades/<id>/annotate` | POST | required | Save pattern + notes |
| `/positions` | GET | required | Positions table |
| `/upload` | GET | required | CSV upload form |
| `/upload` | POST | required | Parse CSVs → ingest → process-trades → redirect |
| `/admin/users` | GET | admin | User list |
| `/admin/users/create` | POST | admin | Create user, display API key once |
| `/admin/users/<id>/deactivate` | POST | admin | Deactivate user |
| `/api/dashboard` | GET | required | JSON data for Chart.js |
| `/api/trades` | GET | required | JSON trades list |

### Session authentication

Add `SessionAuthProvider` to the existing `AuthenticationManager`:
- Validates username + bcrypt password hash against `users` table
- On success: sets `flask.session['user_id']`
- `@login_required`: checks session, redirects to `/login` if absent
- `@admin_required`: checks `is_admin`, returns 403 if not

### Upload workflow

```
POST /upload (multipart/form-data)
  1. Save uploaded files to tempfile.mkdtemp()
  2. CsvParser(include_rolling=request.form.get('include_rolling')).parse_files(paths)
  3. NdjsonIngester(user_id).ingest_records(records)
  4. TradeCompletionEngine(user_id).process_trades()
  5. flash(f"Imported {inserted} new, updated {updated}. {new_trades} trades completed.")
  6. redirect(url_for('trades.index'))
  7. finally: cleanup tempdir
```

### Dashboard charts (Chart.js via `/api/dashboard` JSON)

All data from `DashboardEngine.generate_dashboard()` — no new DB queries:
1. **Equity curve** — line chart: cumulative P&L vs. trade date
2. **Win/loss** — doughnut: winning vs losing count
3. **P&L by pattern** — horizontal bar: net_pnl per setup_pattern
4. **Monthly P&L** — bar chart: sum net_pnl grouped by year-month

### New dependencies (pyproject.toml)

```toml
"flask>=3.0.0",
"flask-session>=0.8.0",
"werkzeug>=3.0.0",
"gunicorn>=21.0.0",
```

Chart.js loaded from CDN in `base.html` (no Python package).

### CLI further pruning in Phase 2

| Removed | Reason |
|---|---|
| `--format {text\|json}` on report commands | Web renders HTML; JSON via `/api/` |
| `--sort-keys` on trades | Web has sortable columns |
| `notes add/show/edit` | Inline edit on `/trades/<id>` |
| `pattern annotate/list/performance` | Pattern selector on trade detail page |

### CLI commands that remain (admin/deployment only)

`db migrate`, `db status`, `db reset`, `db verify-schema`,
`config setup`, `users create`, `users list`, `users regenerate-key`,
`ingest csv`

### Files modified/created (Phase 2)
- `trading_journal/web/__init__.py` — new (`create_app()`)
- `trading_journal/web/auth.py` — new
- `trading_journal/web/routes/*.py` — 6 new modules
- `trading_journal/web/templates/**` — ~10 templates
- `trading_journal/web/static/` — CSS + JS
- `trading_journal/cli.py` — further flag/command pruning
- `wsgi.py` — new Flask WSGI entry point
- `pyproject.toml` — add Flask deps; version bump to `1.0.0`
- `tests/test_web_*.py` — new route tests

---

## Phase 3: Docker Configuration

### Files created

```
Dockerfile
docker-entrypoint.sh
docker-compose.yml           # Local desktop development
docker-compose.prod.yml      # Dokploy production
.dockerignore
.env.example                 # Template for required environment variables
```

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (cached layer — only re-runs when pyproject.toml changes)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "wsgi:app"]
```

### `docker-entrypoint.sh`

```bash
#!/bin/bash
set -e
echo "Running database migrations..."
uv run python main.py db migrate
echo "Migrations complete. Starting server..."
exec "$@"
```

### `docker-compose.yml` — Local desktop development

```yaml
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: trading_journal
      DB_USER: postgres
      DB_PASSWORD: postgres
      FLASK_SECRET_KEY: dev-secret-key-change-in-production
      LOG_LEVEL: DEBUG
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app   # live code reload in dev

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: trading_journal
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### `docker-compose.prod.yml` — Dokploy production

```yaml
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: ${DB_NAME:-trading_journal}
      DB_USER: ${DB_USER:-postgres}
      DB_PASSWORD: ${DB_PASSWORD}
      FLASK_SECRET_KEY: ${FLASK_SECRET_KEY}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME:-trading_journal}
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
```

### `.env.example` — Required environment variables

```bash
# Database
DB_HOST=db
DB_PORT=5432
DB_NAME=trading_journal
DB_USER=postgres
DB_PASSWORD=changeme

# Flask
FLASK_SECRET_KEY=generate-a-random-secret-key-here
LOG_LEVEL=INFO

# First admin user (used by: trading-journal users create)
# Set these then run: docker compose exec app uv run python main.py users create ...
```

### Dokploy deployment steps

1. Push repo to GitHub/GitLab
2. In Dokploy: **New Project → Docker Compose**
3. Point to repo; set compose file to `docker-compose.prod.yml`
4. In Dokploy **Environment** tab, set all variables from `.env.example`
5. Generate `FLASK_SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
6. Deploy → Dokploy builds image, starts services, runs migrations via entrypoint
7. Create first admin user:
   ```bash
   docker compose exec app uv run python main.py users create \
     --username admin --email you@example.com --admin
   ```
8. Configure domain + SSL in Dokploy's **Domains** tab (Traefik handles TLS automatically)

### Config system adaptation for Docker

All config comes from environment variables (already supported — highest priority per `ConfigManager`).
Add a `FLASK_SECRET_KEY` env var to `ConfigManager` so Flask sessions work.

---

## Verification

**Phase 1:**
```bash
uv run python -m pytest tests/test_csv_parser.py -v
uv run python main.py ingest csv ../schwab-csv-to-json/examples/2025-11-24-TradeActivity.csv --dry-run
uv run python main.py ingest csv ../schwab-csv-to-json/examples/2025-11-24-TradeActivity.csv
uv run python main.py db process-trades
uv run python -m pytest
```

**Phase 2:**
```bash
uv run flask --app wsgi:app run --debug
# Visit http://localhost:5000 — login, upload CSV, view dashboard/trades/positions
uv run python -m pytest tests/test_web_*.py -v
```

**Phase 3 (local Docker):**
```bash
docker compose build
docker compose up
# Visit http://localhost:5000
docker compose exec app uv run python main.py users create --username admin --email admin@example.com --admin
docker compose down
```

---

## Version bumps

| Phase | Version | Reason |
|---|---|---|
| Phase 1 complete | `0.4.0` → `0.5.0` | New CSV ingest feature |
| Phase 2 complete | `0.5.0` → `1.0.0` | Major: Flask web app release |
| Phase 3 | no bump | Infrastructure only |
