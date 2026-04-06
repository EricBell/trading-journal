# Module 5: The Web Layer

### Teaching Arc
- **Metaphor:** A post office with a sorting facility. Every web request is a letter that arrives at the front door (Flask). The sorting room (routes/) reads the address and hands it to the right department (auth, trades, admin, journal...). Each department prepares a response and sends it back. The letter never reaches the wrong department.
- **Opening hook:** "You open your browser and type the URL. Somewhere, a Python function is about to run. Here's exactly which one, how it knows who you are, and how your data comes back as a web page."
- **Key insight:** Flask's "blueprint" system divides the web app into departments. Each department (auth, dashboard, trades, positions, admin, journal) is its own file that handles one area of the app. Authentication uses two strategies: session cookies for the browser, API keys for automated scripts.
- **"Why should I care?":** When you want to add a new page, knowing the blueprint structure means you can tell AI "add a new route in the journal blueprint" instead of "add a page somewhere." When something breaks, knowing the auth flow tells you where to look.

### Code Snippets (pre-extracted)

**Flask app factory** — trading_journal/web/__init__.py (describe this: the create_app() function registers all blueprints). Use this representative auth snippet instead:

**The login route structure** — trading_journal/web/routes/auth.py. Use this conceptual description since we don't have the exact snippet: The login route accepts POST, checks username/password hash against the users table, sets session['user_id'], and redirects to dashboard. Use this actual route from the file map.

**Ingest route — receives CSV upload, calls the pipeline** — trading_journal/web/routes/ingest.py. This handles multipart POST, auto-detects file format (CSV vs NDJSON), calls CsvParser or NdjsonIngester, and shows results.

Use this snippet from models.py via a description of the users table columns:

**Session + API key auth pattern** — conceptual description:
- Web browser: stores `session['user_id']` as an encrypted cookie. Each request, Flask checks if session has a user_id, looks up that user in the DB.
- API calls: send `X-API-Key: <key>` header. Flask hashes the key with SHA256 and looks for a match in `users.api_key_hash`.
- `@login_required` decorator: wraps route functions to redirect to /login if no session.
- `@admin_required` decorator: additionally checks `users.is_admin == True`.

**The routes blueprint registration** — web/__init__.py — describe the structure:
The create_app() function registers 10 blueprints:
- auth_bp → /login, /logout
- dashboard_bp → /
- trades_bp → /trades, /trades/<id>
- positions_bp → /positions
- ingest_bp → /ingest
- admin_bp → /admin/*
- journal_bp → /journal
- about_bp → /about
- settings_bp → /settings
- api_bp → /api/*

### Interactive Elements

- [x] **Data flow animation** — "A request to /trades" — actors: [Browser, Nginx, Gunicorn, Flask Router, `@login_required`, trades.py route, SQLAlchemy, PostgreSQL, Jinja2 Template]. Steps:
  1. Browser sends GET /trades
  2. Nginx receives it, forwards to Gunicorn (the Python process manager)
  3. Gunicorn passes to Flask
  4. Flask router matches /trades → trades blueprint
  5. `@login_required` decorator checks session['user_id'] — is the user logged in?
  6. Route function queries PostgreSQL via SQLAlchemy: "get completed_trades for this user_id"
  7. Results passed to Jinja2 template: trades.html
  8. HTML rendered and sent back to browser
- [x] **Group chat animation** — "Who are you?" auth challenge. Browser: "GET /trades." `@login_required`: "Show me your session cookie." Browser: "Here's session_id=abc123." `@login_required`: "Looking you up... user_id=7. You're Eric. Allowed." trades.py: "Great — loading Eric's trades now." — Second scenario: API Script: "GET /api/trades, X-API-Key: sk_xyz." `@login_required`: "Hashing that key... found user_id=7 in the database. You're in." API Script: "Thanks. Give me JSON."
- [x] **Architecture diagram** — visual "blueprint map" showing the 10 blueprints as rooms in a building. The front door is Flask. Each room has its URL prefix and a one-liner description. Admin rooms are marked "Authorized Personnel Only."
- [x] **Quiz** — 3 questions:
  1. "You want to add a /watchlist page. Which file would you create and where?" (A new watchlist.py in trading_journal/web/routes/, then register it as a blueprint in web/__init__.py)
  2. "A user is logged in via browser but getting 401 errors from the API. Why?" (The API uses API key auth, not session cookies — the user needs to pass X-API-Key header, not just be logged in to the web UI)
  3. "The admin route at /admin/export is showing to non-admin users. Where's the bug?" (The @admin_required decorator is missing or misconfigured on that route in admin.py)

### Reference Files to Read
- `references/interactive-elements.md` → "Data Flow Animation", "Group Chat Animation", "Multiple-Choice Quizzes"
- `references/design-system.md` → card styles for the blueprint map
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include

### Connections
- **Previous module:** "The Clever Engineering" — covered the algorithmic core (UPSERT, avg cost, reprocessing). This module covers the web interface that exposes that core to users.
- **Next module:** "Steering the AI" — uses everything learned to help the learner make better decisions when directing AI to extend or debug this codebase.
- **Tone/style notes:** Teal accent. Flask and Jinja2 need tooltip definitions. "Blueprint" is a Flask-specific term (tooltip it). Gunicorn needs a tooltip (it's the Python web server). Nginx needs a tooltip (it's the traffic director that sits in front of Gunicorn).
