# QKB Intelligence

## Honest assessment of where this stands

What exists today is a scraper that copies opencorporates.al into a PostgreSQL database. That is not a product. Opencorporates.al already does company search, and QKB is the authoritative source. A user has no reason to use this over either of those — yet.

The value is not in the data. It's in the queries that become possible once the data is relational. Specifically:

| Query | QKB | opencorporates.al | This product |
|-------|-----|-------------------|-------------|
| Look up one company by NIPT | Yes | Yes | Yes |
| Search by company name | Yes | Yes | Yes |
| "Show me every company where X is a shareholder" | No | No | **Yes** |
| "Show me every company where X is an administrator" | No | No | **Yes** |
| "What changed about this company since last month?" | No | No | **Yes (after nightly re-scrapes accumulate)** |
| "Export 50 company profiles to CSV for KYC" | No | No | **Not yet, but trivial to add** |
| "Show me the ownership chain: who owns Company A through which entities" | No | No | **Data model supports it, UI doesn't yet** |

The first two rows are table stakes. Rows 3-6 are why someone would pay. None of those are built yet. That's what needs to happen next.

---

## Who pays for this

- **Banks** — legally required to do KYC/AML checks on every business client. A compliance officer currently opens QKB, searches one company, downloads a PDF, then repeats for every shareholder. This product does it in one search.
- **Law firms** — due diligence on counterparties. "Is this person connected to other companies?" is the core question. QKB can't answer it.
- **Foreign investors** — evaluating Albanian companies before entering deals. Need structured data they can import into their own systems, not individual PDFs.
- **Accounting/audit firms** — client onboarding requires verifying company details and ownership structures.

Realistic market size in Albania: ~200 potential paying customers. At EUR 29-79/month, ceiling is EUR 5-15k/month. Gets bigger with Kosovo expansion (same language) and if international due diligence firms become buyers.

---

## What's built

### Data model
- **Company** — core entity identified by NIPT. Name, legal form, status, capital, city, address, registration date, NACE activity.
- **Shareholder** — linked to Company via FK. Individual or company type. Ownership percentage. `parent_company` FK enables ownership chain traversal between companies in the DB.
- **LegalRepresentative** — administrators and board members with role classification.
- **OwnershipChange** — historical diffs. Each re-scrape compares current shareholders against what's in the DB. If different, logs the before/after as JSON snapshots with date.
- **ScrapeLog** — monitoring. Counts of scraped/new/updated/errors per run.

### Scraper pipeline
Two-phase process in `companies/scraper.py`:

1. **Collect NIPTs** from opencorporates.al listing APIs (JSON endpoints). Six categories, ~5,140 unique NIPTs total.
2. **Scrape detail pages** at `/en/nipt/{NIPT}`. Parses HTML table structure (`<th>` labels, `<td>` values) into structured fields.
3. **Upsert** into Django models with ownership change detection.

Additional features:
- **On-demand scraping** — when a user searches for a NIPT not in the DB, a Celery task fetches it in the background. Search page shows "fetching, refresh in 30 seconds." User demand drives coverage.
- **Management command** — `uv run python manage.py scrape` with `--categories` and `--limit` flags.

### Authentication & access control
- Custom `User` model with email verification, `is_premium` flag, search rate tracking, GDPR data export/deletion
- Google OAuth via `social-auth-app-django` (pipeline handles existing-user linking, profile creation, welcome emails)
- Email verification flow: signup → verification email (console in dev, SMTP in prod) → click link → account activated
- All company views require login (`@login_required`)
- **Search rate limiting:** free users get 10 searches/day (counter resets at midnight), premium/superuser unlimited
- User dashboard with profile management, plan usage stats, GDPR data export, and account deletion

### Search
- **Full-text search** using PostgreSQL `SearchVectorField` with `SearchQuery`/`SearchRank` for ranked results
- `search_vector` populated on every scraper upsert (`SearchVector('name', 'name_latin', 'nipt', 'city')`)
- Backfill command: `uv run python manage.py populate_search_vectors`
- Falls back to `icontains` for companies without populated search vectors

### Production readiness
- **Security headers** enabled when `DEBUG=False`: HSTS, SSL redirect, secure cookies, content-type nosniff
- **Email backend** env-configurable (`EMAIL_BACKEND`, `EMAIL_HOST`, etc.)
- **Celery Beat** nightly full scrape at 3:00 AM
- **Per-task time limits:** full scrape 4h, single NIPT 2min
- **Error pages:** custom 403, 404, 500 extending shared base template

### UI
- `/` — search with full-text ranking, rate limiting, upgrade prompts (login required)
- `/company/<nipt>/` — company detail with shareholders, representatives, ownership history (login required)
- `/accounts/login/` — login with email/password or Google OAuth
- `/accounts/signup/` — registration with email verification
- `/accounts/dashboard/` — user dashboard with profile, "Your Plan" usage card, GDPR data management
- `/accounts/pricing/` — three-tier pricing page (Free / Professional EUR 29/mo / Business EUR 79/mo)
- `/admin/` — Django admin with inlines for data QA
- All pages share navbar via `base.html` (companies pages use dark theme override)

### What's been tested
- 17 Albanian banks scraped end-to-end with correct extraction of names, legal forms, capital, shareholders (including parent company names extracted from free-text), administrators, and board members.

---

## What's not built (and what matters)

### Must-have for first paying customer
- [ ] **Cross-entity person search** — "Show me every company where Agron Mustafa appears." This is the #1 feature that differentiates from QKB/opencorporates. It's a single Django query across Shareholder and LegalRepresentative tables. Half a day of work.
- [ ] **Seed the 5,000 high-value companies** — run the full scrape. The scraper works, just needs to run for ~2.5 hours.
- [x] ~~**Nightly re-scrape via Celery Beat**~~ — configured at 3:00 AM. Change detection accumulates over time.
- [x] ~~**Full-text search**~~ — `SearchVector`/`SearchQuery`/`SearchRank` on name, name_latin, nipt, city. Populated on upsert + backfill command.
- [x] ~~**Rate limiting + tiered access**~~ — free users: 10/day, premium: unlimited. Upgrade prompts on search page and dashboard.
- [x] ~~**Pricing page**~~ — `/accounts/pricing/` with Free/Professional/Business tiers.

### Should-have for first 10 customers
- [ ] Bulk CSV export of search results
- [ ] Payment gateway integration (currently manual bank transfer)

### Nice-to-have (build only if customers ask)
- [ ] Ownership chain visualization (graph UI)
- [ ] REST API (DRF)
- [ ] Change alert emails ("Company X changed ownership")
- [ ] English translations of Albanian fields
- [ ] PDF company reports

---

## Data strategy

### How much to scrape

**5,000 companies is enough to launch.** These are the companies people actually do due diligence on — public contractors, banks, concessions, state-owned enterprises. Nobody pays EUR 29/month to look up a sole proprietor barbershop.

Do not try to scrape 200k+ companies upfront:
- Takes weeks, not hours
- Risk of getting rate-limited or blocked
- 95% of the data will never be viewed
- Time spent scraping is time not spent talking to customers

Coverage grows organically through the on-demand scrape (user searches for unknown NIPT, background task fetches it).

### Historical changes — don't reconstruct, start recording

There is no way to reconstruct historical ownership changes from the data available. Opencorporates.al shows current state plus a free-text "Changes" paragraph in Albanian. Parsing that paragraph into structured events is possible but extremely messy and low-ROI.

Instead: **start recording changes going forward.** The `OwnershipChange` model already diffs shareholders on every re-scrape. After 6 months of nightly scrapes, you have 6 months of structured change history. After a year, a year. This dataset compounds and becomes a moat — nobody else has it.

Celery Beat is now configured — nightly scrape runs at 3:00 AM. Start it with:
```bash
uv run celery -A config beat -l info
```

### Seeding the database

Recommended order (highest value, smallest set first):

```bash
uv run python manage.py scrape --categories banka           # 17 banks (~30s)
uv run python manage.py scrape --categories publike          # 303 state-owned (~8min)
uv run python manage.py scrape --categories concession       # 288 PPP (~7min)
uv run python manage.py scrape --categories jobanka          # 40 non-bank (~1min)
uv run python manage.py scrape --categories companyinvestor  # 61 investors (~2min)
uv run python manage.py scrape --categories company          # 4,431 contractors (~2hrs)
```

---

## Known issues and how to handle them

### 1. Opencorporates.al will break or block you

They will change their HTML structure, add rate limiting, or go down. This is certain.

**Mitigations already in place:**
- `ScrapeLog` tracks errors per run — check daily.
- Raw HTML stored on each Company record — re-parse without re-fetching if parser breaks.
- `REQUEST_DELAY` (1.5s) is polite. Increase to 3-5s if they complain.
- User-Agent identifies the bot.

**If HTML structure changes:**
Only `_parse_detail_table()` in `scraper.py` needs updating. The rest of the pipeline (collection, upsert, change detection) is decoupled from the parser.

**If they block you entirely:**
Scrape QKB directly (the actual government registry) or use the official gazette. The data is public; opencorporates.al is just one access point.

### 2. Shareholder parsing is ~80-90% accurate

The owner field is free-text Albanian with inconsistent formatting. Some entries use Roman numerals, some don't. Some quote company names, some don't. Some list percentages, some don't.

**Don't try to make it perfect.** Get it to 80-90% and add manual corrections through Django admin. Early users will report errors. Fix those specific cases. That feedback loop is more efficient than anticipating every edge case.

Current known parsing issues:
- Companies with many shareholders (8+) may have some entries merged or missed due to Roman numeral splitting
- Percentage extraction sometimes pulls from the wrong part of the text
- Some shareholders classified as "individual" when they should be "company" (detection relies on keyword matching)

### 3. Duplicate companies across categories

Same company can appear in multiple listing categories (a bank that's also a public contractor). Handled by NIPT unique constraint — `update_or_create` on NIPT means duplicates just update the existing record.

### 4. Legal/ethical considerations

The data is public. Opencorporates.al is an NGO transparency project that exists to make this data accessible. The underlying data comes from QKB, Albania's official business registry.

Be a good citizen:
- Keep rate limiting polite
- Identify your bot in User-Agent
- Don't hammer their servers during business hours
- If they ask you to stop, stop and find another data source

### 5. The biggest risk: building instead of selling

The product works. The temptation is to add ownership graphs, PDF export, API endpoints, English translations, a better UI, and 15 other features before showing it to anyone.

**Don't.** The product is the search box and the cross-entity query capability. Show it to 5 people this week. Their reactions tell you what to build next. Everything else is procrastination.

---

## Pricing model

| Tier | Price | Features | Status |
|------|-------|----------|--------|
| Free | EUR 0 | 10 searches/day, basic company info | Live |
| Professional | EUR 29/month | Unlimited search, full details, ownership chains | Live (manual activation) |
| Business | EUR 79/month | API access, bulk export, priority support | Contact CTA |

---

## Scaling beyond Albania

The same product works in every country with a messy company registry. The technical pattern is identical: scrape, structure, search.

**Near-term (same language):**
- Kosovo (ARBK registry) — doubles the market overnight

**Medium-term (Balkans):**
- Serbia (APR), North Macedonia (CRRM), Montenegro (CRPS), Bosnia
- Sold as "Balkan Company Intelligence" to Vienna/Zurich/London law firms doing cross-border deals
- Those firms pay EUR 200-500/month

**Long-term (emerging markets):**
- Central Asia, Caucasus, MENA, Sub-Saharan Africa
- Buyers become international banks and due diligence firms (Kroll, Control Risks)
- They currently pay local researchers $500/day for manual registry pulls
- That's a $10M+ ARR business if you cover 20-30 countries

But none of that matters until 5 people in Tirana are paying you EUR 29/month.

---

## Technical reference

### Stack
- Python 3.13, managed with `uv`
- Django 6.0 + PostgreSQL (database: `qkb`)
- Celery + Redis (broker: `redis://localhost:6379/1`)
- httpx + BeautifulSoup + lxml for scraping
- django-environ for settings
- social-auth-app-django for Google OAuth
- Pillow for avatar uploads

### Commands
```bash
uv run python manage.py runserver 8001      # Dev server
uv run python manage.py scrape              # Scrape all categories
uv run python manage.py scrape --categories banka --limit 5  # Test run
uv run python manage.py populate_search_vectors  # Backfill search vectors
uv run python manage.py makemigrations      # After model changes
uv run python manage.py migrate             # Apply migrations
uv run celery -A config worker -l info      # Celery worker
uv run celery -A config beat -l info        # Celery Beat (nightly scrape)
```

### Project structure
```
qkb/
├── config/                        # Django settings, urls, celery
├── accounts/                      # User auth app
│   ├── models.py                  # User (with search rate tracking), UserProfile, EmailVerificationLog, ClickTracking
│   ├── views/                     # auth.py, user.py, emails.py, analytics.py, static.py (incl. pricing)
│   ├── pipeline.py                # Social auth pipeline (Google OAuth)
│   ├── forms.py                   # Signup, login, profile update forms
│   ├── urls.py                    # /accounts/ namespace
│   └── templates/accounts/        # Login, signup, dashboard, verification, privacy, pricing
├── companies/
│   ├── models.py                  # Company, Shareholder, LegalRepresentative, OwnershipChange, ScrapeLog
│   ├── scraper.py                 # Two-phase pipeline: listing APIs -> detail pages -> DB upsert
│   ├── tasks.py                   # Celery: run_full_scrape_task, scrape_single_nipt_task
│   ├── views.py                   # search (full-text + rate limiting), company_detail
│   ├── admin.py                   # Full admin with inlines
│   ├── urls.py                    # / and /company/<nipt>/
│   └── management/commands/
│       ├── scrape.py              # Scrape management command
│       └── populate_search_vectors.py  # Backfill search vectors
├── templates/                     # Project-level templates
│   ├── base.html                  # Shared layout (Bootstrap 5, nav, messages)
│   ├── 404.html                   # Error pages (also 403.html, 500.html)
│   └── ...
├── .env                           # Credentials + Google OAuth keys (not committed)
└── pyproject.toml                 # uv dependencies
```

### Key files for future work
- **To fix parsing bugs:** `companies/scraper.py` -> `_parse_detail_table()`, `_parse_owner_string()`
- **To add new features:** `companies/views.py` (new views), `companies/urls.py` (new routes)
- **To add new data sources:** Create a new scraper module, same pattern as `scraper.py`
- **To add API:** `uv add djangorestframework`, add serializers + viewsets
- **To change search fields:** Update `SearchVector(...)` in `scraper.py:upsert_company()` and re-run `populate_search_vectors`
- **To change rate limits:** Edit `FREE_DAILY_LIMIT` in `companies/views.py`
- **To grant premium access:** Set `user.is_premium = True` in Django admin
- **To configure Google OAuth:** Add `GOOGLE_OAUTH2_KEY` and `GOOGLE_OAUTH2_SECRET` to `.env`
- **To configure email for production:** Set `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in `.env`

---

## The one thing to do next

Seed the 5,000 companies, start Celery Beat, and go talk to a bank compliance officer.
