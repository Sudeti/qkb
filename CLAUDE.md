# QKB Intelligence

Albanian Company Registry search and analytics platform. Scrapes opencorporates.al (which aggregates QKB data), structures it into relational models, and serves it as a searchable database with ownership chain mapping.

## Stack

- **Python 3.13** managed with `uv`
- **Django 6.0** with PostgreSQL (`qkb` database)
- **Celery + Redis** for async scraping tasks (broker on `redis://localhost:6379/1`)
- **django-environ** for settings via `.env`
- **httpx + BeautifulSoup + lxml** for scraping
- **social-auth-app-django** for Google OAuth login
- **Pillow** for avatar image uploads

## Project structure

```
qkb/
├── config/          # Django project config (settings, urls, celery, wsgi)
├── accounts/        # User auth app (custom User model, Google OAuth, email verification, GDPR)
│   ├── models.py    # User, UserProfile, EmailVerificationLog, ClickTracking
│   ├── views/       # Split into auth.py, user.py, emails.py, analytics.py, static.py
│   ├── pipeline.py  # Social auth pipeline (Google OAuth user creation/linking)
│   ├── forms.py     # Signup, login, profile update forms
│   ├── urls.py      # /accounts/ namespace
│   └── templates/accounts/  # Login, signup, dashboard, profile, verification, privacy, pricing
├── companies/       # Main app
│   ├── models.py    # Company, Shareholder, LegalRepresentative, OwnershipChange, ScrapeLog
│   ├── admin.py     # Full admin with inlines for shareholders/reps/changes
│   ├── views.py     # search (full-text + rate limiting), company_detail — @login_required
│   ├── urls.py      # / and /company/<nipt>/
│   ├── scraper.py   # Two-phase scraper: listing API -> detail page parser -> DB upsert
│   ├── tasks.py     # Celery tasks: run_full_scrape_task, scrape_single_nipt_task
│   └── management/commands/
│       ├── scrape.py                  # Management command for scraping
│       └── populate_search_vectors.py # Backfill search_vector for all companies
├── templates/       # Project-level templates
│   ├── base.html    # Base template with Bootstrap 5, nav bar, messages
│   ├── 404.html     # Error page
│   ├── 403.html     # Error page
│   └── 500.html     # Error page
├── .env             # DB creds, Redis URL, Google OAuth keys (not committed)
└── pyproject.toml   # uv dependencies
```

## Commands

All commands use `uv run` — no need to activate a venv.

```bash
uv run python manage.py runserver 8001    # Dev server (port 8001)
uv run python manage.py makemigrations    # After model changes
uv run python manage.py migrate           # Apply migrations
uv run python manage.py createsuperuser   # Admin user
uv run python manage.py shell             # Django shell
uv run celery -A config worker -l info    # Celery worker for async scraping
uv run celery -A config beat -l info      # Celery Beat (nightly scrape at 3 AM)

# Scraping
uv run python manage.py scrape                          # Scrape all categories
uv run python manage.py scrape --categories banka       # Scrape only banks
uv run python manage.py scrape --categories publike concession --limit 50  # Test run
uv run python manage.py populate_search_vectors         # Backfill search vectors
```

## Scraper architecture

Two-phase pipeline in `companies/scraper.py`:

1. **Phase 1 — Collect NIPTs** from opencorporates.al listing APIs (JSON endpoints):
   - `/sq/company/any` — ~4,431 public contractors
   - `/sq/publike/any` — ~303 state-owned
   - `/sq/concession/any` — ~288 PPP/concessions
   - `/sq/banka/any` — ~17 banks
   - `/sq/jobanka/any` — ~40 non-bank financial
   - `/sq/companyinvestor/any` — ~61 strategic investors

2. **Phase 2 — Scrape detail pages** at `/en/nipt/{NIPT}`. The detail page is an HTML table with `<th>` labels and `<td>` values. Fields extracted: name, legal form, status, capital, registration date, city, address, administrators, board members, shareholders.

3. **Phase 3 — Upsert** into Django models with ownership change detection (diffs current vs previous shareholders).

**On-demand scraping:** When a user searches for a NIPT not in the DB, a Celery task fires to scrape that single company. The search page shows "fetching, refresh in 30s."

**Rate limiting:** 1.5s delay between requests. User-Agent identifies the bot.

## Key models

- **Company** — core entity, identified by `nipt` (unique tax ID). Has `SearchVectorField` for full-text search.
- **Shareholder** — linked to Company. Can be `individual` or `company` type. `parent_company` FK enables ownership chain traversal.
- **LegalRepresentative** — administrator/director/board member of a company.
- **OwnershipChange** — historical diffs of shareholder changes (old/new snapshots as JSON).
- **ScrapeLog** — tracks each scraping run (counts, errors, status).

## Architecture decisions

- **Scraper runs separately from web app** (Celery task or management command). If scraper breaks, product stays up.
- **NIPT is the primary lookup key** — all URLs and external references use NIPT, not Django auto-IDs.
- **Ownership chains** modeled via Shareholder `parent_company` FK back to Company.
- **Raw HTML stored** on each Company for debugging and re-parsing if parser improves.
- **On-demand scraping** — user searches drive coverage expansion organically.

## Authentication

- **Custom User model** (`accounts.User`) with email verification, `is_premium` flag, search rate tracking (`searches_today`, `searches_reset_date`), and GDPR data export/deletion.
- **Google OAuth** via `social-auth-app-django`. Pipeline in `accounts/pipeline.py` handles existing-user linking, profile creation, and welcome emails.
- **Email verification** — new users are inactive until they click a verification link. Email backend is env-configurable (console in dev, SMTP in production).
- **`@login_required`** on all companies views — unauthenticated users redirect to `/accounts/login/`.
- **Search rate limiting** — free users get 10 searches/day with counter reset at midnight. Premium users and superusers are unlimited. Rate limit banner on search page links to pricing.
- **URL namespaces:** `accounts:` (login, signup, dashboard, pricing, etc.) and `social:` (Google OAuth flow).
- **`.env` keys for Google OAuth:** `GOOGLE_OAUTH2_KEY`, `GOOGLE_OAUTH2_SECRET` (optional, sign-in button shows but won't work without them).

## Conventions

- Use `uv add <package>` to add dependencies, not pip.
- Templates in `companies/templates/companies/` and `accounts/templates/accounts/` (app-namespaced). Project-level `templates/base.html` for the shared layout.
- URL namespace is `companies:` (e.g., `{% url 'companies:search' %}`), `accounts:` for auth views.
- Admin is the primary data QA tool during development.
- Scraping logic lives in `scraper.py`, Celery wrappers in `tasks.py`.

## Production readiness

- **Security headers** — `SECURE_SSL_REDIRECT`, `HSTS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF` all enabled when `DEBUG=False`.
- **Email** — env-configurable backend (`EMAIL_BACKEND`, `EMAIL_HOST`, etc.). Console in dev, SMTP in production.
- **Celery Beat** — nightly full scrape at 3:00 AM. Run with `uv run celery -A config beat -l info`.
- **Per-task time limits** — full scrape: 4h hard / 3h50m soft. Single NIPT: 2min hard / 90s soft.
- **Full-text search** — `search_vector` populated on every upsert via `SearchVector('name', 'name_latin', 'nipt', 'city')`. Search view uses `SearchQuery`/`SearchRank` with `icontains` fallback.
- **Rate limiting** — free users: 10 searches/day. Premium/superuser: unlimited. Counter resets daily.
- **Pricing page** — `/accounts/pricing/` with Free (EUR 0), Professional (EUR 29/mo), Business (EUR 79/mo).
- **Error pages** — custom 403, 404, 500 templates extending base.html.
- **Shared navbar** — all pages (companies + accounts) extend `base.html` with consistent navigation.

## What's not built yet

- **API (DRF)** — not added yet. Add when banks/law firms need programmatic access.
- **Ownership chain visualization** — data model supports it, UI doesn't render graphs yet.
- **Bulk CSV export** — not yet implemented.
- **Payment gateway** — pricing page shows contact CTA; no Stripe/payment integration.

## Database

PostgreSQL database named `qkb`. Credentials in `.env`. To recreate:

```bash
createdb qkb
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py scrape --categories banka  # seed with banks first
uv run python manage.py populate_search_vectors    # backfill search vectors
```
