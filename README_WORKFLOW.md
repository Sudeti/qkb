# QKB Intelligence

Albanian Company Registry intelligence platform. Scrapes company data, structures it relationally, and serves it as a searchable database with ownership chain mapping, change detection, and (soon) public procurement cross-linking.

**Live at:** https://thelbi.al

---

## The core idea

The Albanian business registry (QKB) and opencorporates.al let you look up one company at a time. That's it. They can't answer:

| Query | QKB / opencorporates.al | This product |
|-------|------------------------|--------------|
| Look up one company by NIPT | Yes | Yes |
| Search by company name | Yes | Yes |
| "Show me every company where X is a shareholder" | No | **Yes** |
| "Show me every company where X is an administrator" | No | **Yes** |
| "What changed about this company since last month?" | No | **Yes** (nightly change detection) |
| "Alert me when this company's ownership changes" | No | **Planned** |
| "This company just won a EUR 2M tender — who owns it?" | No | **Planned** (APP integration) |
| "Export 50 company profiles to CSV for KYC" | No | **Planned** |
| "Show me the ownership chain through entities" | No | **Data model ready, UI not yet** |

Rows 3-9 are why someone would pay. The cross-entity queries and the procurement cross-linking are what no one else in Albania offers.

---

## Who pays for this

- **Banks** — legally required to do KYC/AML checks on every business client. A compliance officer currently opens QKB, searches one company, downloads a PDF, then repeats for every shareholder. This product does it in one search.
- **Law firms** — due diligence on counterparties. "Is this person connected to other companies?" is the core question.
- **Foreign investors** — evaluating Albanian companies before entering deals. Need structured data, not individual PDFs.
- **Accounting/audit firms** — client onboarding requires verifying company details and ownership.
- **Journalists/NGOs** — investigating who's behind companies winning public tenders.

Realistic market size in Albania: ~200 potential paying customers. At EUR 29-79/month, ceiling is EUR 5-15k/month. Grows with Kosovo expansion and international due diligence firms.

---

## What's built and deployed

### Infrastructure (live on DigitalOcean)

- **Server:** DigitalOcean droplet (1 vCPU, 1GB RAM + 1GB swap), Ubuntu
- **Domain:** thelbi.al with SSL (Let's Encrypt)
- **Web server:** Nginx reverse proxy -> Gunicorn (2 workers) via Unix socket
- **Background tasks:** Celery worker + Celery Beat as systemd services
- **Database:** PostgreSQL (`qkb` database)
- **Cache/broker:** Redis (db 1)
- **Deploy:** `./deploy.sh` — pulls code, syncs deps, migrates, collects static, restarts all services

### Systemd services

| Service | File | Command |
|---------|------|---------|
| Gunicorn | `/etc/systemd/system/qkb.service` | `sudo systemctl restart qkb` |
| Celery Worker | `/etc/systemd/system/qkb-celery.service` | `sudo systemctl restart qkb-celery` |
| Celery Beat | `/etc/systemd/system/qkb-celerybeat.service` | `sudo systemctl restart qkb-celerybeat` |
| Nginx | `/etc/nginx/sites-available/qkb` | `sudo systemctl reload nginx` |

```bash
# Check all services at once
sudo systemctl status qkb qkb-celery qkb-celerybeat nginx --no-pager

# Restart all QKB services
sudo systemctl restart qkb qkb-celery qkb-celerybeat

# Reload after editing systemd unit files
sudo systemctl daemon-reload

# Logs (follow)
sudo journalctl -u qkb -f              # Gunicorn
sudo journalctl -u qkb-celery -f       # Celery worker
sudo journalctl -u qkb-celerybeat -f   # Celery Beat

# Logs (last 50 lines)
sudo journalctl -u qkb -n 50 --no-pager
sudo journalctl -u qkb-celery -n 50 --no-pager

# Nginx
ls /etc/nginx/sites-available/         # List all site configs
ls /etc/nginx/sites-enabled/           # List enabled configs
sudo nginx -t                          # Test config before reload
sudo systemctl restart nginx

# Gunicorn socket
ls -la /run/gunicorn/                  # Check socket file exists

# Edit service files
sudo nano /etc/systemd/system/qkb.service
sudo nano /etc/systemd/system/qkb-celery.service
sudo nano /etc/systemd/system/qkb-celerybeat.service
sudo nano /etc/nginx/sites-available/qkb
```

### Deploy script

```bash
ssh root@thelbi.al
cd /var/www/qkb && ./deploy.sh
```

The script: pulls latest from `origin main`, runs `uv sync`, runs migrations, collects static, restarts Gunicorn + Celery + Celery Beat + Nginx.

### Data pipeline

Two-phase scraper in `companies/scraper.py`:

1. **Phase 1 — Collect NIPTs** from opencorporates.al listing APIs (6 categories, ~5,140 companies)
2. **Phase 2 — Scrape detail pages** at `/en/nipt/{NIPT}`, parse HTML tables into structured fields
3. **Phase 3 — Upsert** into Django models with ownership change detection (diffs current vs previous shareholders)

Additional:
- **Nightly scrape** via Celery Beat at 3:00 AM UTC — keeps data fresh and accumulates change history
- **On-demand scraping** — when a user searches for a NIPT not in the DB, Celery fetches it in background

### Authentication & access control

- Custom `User` model with email verification, `is_premium` flag, search rate tracking
- Google OAuth via `social-auth-app-django`
- All company views require `@login_required`
- Free users: 10 searches/day (resets at midnight). Premium/superuser: unlimited.
- GDPR: data export + account deletion

### Search

- PostgreSQL full-text search (`SearchVectorField` + `SearchQuery` + `SearchRank`)
- NIPT exact match tried first, then full-text, then `icontains` fallback
- **Note:** full-text search matches whole words, not substrings. "komb" won't match via FTS but will match via the `icontains` fallback.

### Current user flow

1. Visit thelbi.al -> see public landing page (logged-in users redirect to `/search/`)
2. Sign up (email + username + password) -> verify email -> login
3. Dashboard shows search usage stats
4. Search by company name or NIPT
5. Click result -> company detail (shareholders, representatives, ownership changes)
6. If NIPT not in DB -> Celery scrapes it on demand, user told to refresh in 30s
7. Free users hit limit -> see upgrade banner linking to pricing page

---

## Payments: bank transfer, not Stripe

Stripe doesn't work well in Albania. That's fine. The target customers are businesses (banks, law firms, accounting firms) — they pay invoices via bank transfer. This is standard B2B in the Balkans.

### Pricing tiers

| Tier | Price | What they get |
|------|-------|---------------|
| Free | EUR 0 | 10 searches/day, basic company info |
| Professional | EUR 29/month | Unlimited searches, ownership chains, shareholder history |
| Business | EUR 79/month | Everything + API access, bulk export, priority support |

### Upgrade workflow

1. User hits rate limit or visits `/accounts/pricing/` — sees tier comparison
2. Clicks "CONTACT US" → sends email to `info@qkb.al` with subject line pre-filled
3. You reply with a proforma invoice (bank details + amount + period)
4. They pay via bank transfer
5. You activate premium in Django admin (see below)
6. They get unlimited access immediately

### Activating / deactivating premium

**Via Django admin (preferred):**
```
https://thelbi.al/admin/accounts/user/
```
Find the user → check `is_premium` → Save.

**Via Django shell (on server):**
```bash
/var/www/qkb/.venv/bin/python manage.py shell
```
```python
from accounts.models import User

# Activate premium
user = User.objects.get(email='client@example.com')
user.is_premium = True
user.save(update_fields=['is_premium'])

# Deactivate premium (non-payment, churn)
user = User.objects.get(email='client@example.com')
user.is_premium = False
user.save(update_fields=['is_premium'])

# List all premium users
User.objects.filter(is_premium=True).values_list('email', 'username', 'date_joined')

# Check a user's search usage
user = User.objects.get(email='client@example.com')
print(f"Searches today: {user.searches_today}, Reset date: {user.searches_reset_date}, Premium: {user.is_premium}")
```

### What to build next
- Invoice template (PDF proforma with Albanian bank details)
- Admin action to bulk-toggle premium status

---

## The killer feature: public procurement cross-linking

This is the feature that turns QKB Intelligence from "nice lookup tool" into "I can't do my job without this."

### What it is

When a company wins a public tender, cross-reference it with your company registry data to instantly show:
- Who owns the company (shareholders, ownership percentages)
- Who manages it (administrators, board members)
- What other companies those people own or manage
- Whether ownership recently changed (common before tender awards)

**Example output:** "ALBTELECOM sha just won a EUR 2M infrastructure tender from the Ministry of Transport. ALBTELECOM is 100% owned by CETEL Group, which is owned by Calik Holding (Turkey). The legal representative is X, who is also administrator of companies Y and Z."

### Why it matters

- **Journalists** currently spend days manually connecting these dots
- **Compliance officers** at banks need to check if their clients are winning government contracts (PEP screening)
- **Competitors** want to know who's winning in their sector
- **Anti-corruption NGOs** want to track patterns (same people winning across entities)
- **No one in Albania automates this cross-linking today**

### Data source: APP (Agjencia e Prokurimit Publik)

The Albanian Public Procurement Agency publishes tender results. The data includes:
- Winning company name and NIPT
- Tender value (in ALL/EUR)
- Contracting authority (which government body)
- Tender category (construction, IT, services, etc.)
- Award date

**Format:** Published as weekly PDF bulletins + the APP electronic procurement platform.

### Technical integration plan

#### New model: `Tender`

```python
class Tender(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tenders')
    title = models.TextField()                          # Tender description
    contracting_authority = models.CharField(max_length=500)  # Ministry, municipality, etc.
    value = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    currency = models.CharField(max_length=3, default='ALL')  # ALL or EUR
    category = models.CharField(max_length=200, blank=True)
    award_date = models.DateField()
    source_url = models.URLField(blank=True)            # Link to APP bulletin
    raw_text = models.TextField(blank=True)             # Original text for debugging
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['award_date']),
            models.Index(fields=['company', '-award_date']),
        ]
```

#### New scraper: `tenders/scraper.py`

Pipeline:
1. Download weekly APP PDF bulletins (or scrape the e-procurement platform)
2. Parse PDF tables using `pdfplumber` or `tabula-py` to extract structured rows
3. Match winning company to existing `Company` records via NIPT
4. If company not in DB, trigger on-demand scrape (same as search)
5. Create `Tender` record linked to `Company`

#### New Celery task: weekly tender scrape

```python
# In Celery Beat schedule, alongside the nightly company scrape:
'weekly-tender-scrape': {
    'task': 'tenders.tasks.scrape_tenders_task',
    'schedule': crontab(day_of_week=1, hour=6, minute=0),  # Monday 6 AM
},
```

#### Alerts

When a new `Tender` is created for a watched company, email the user:

```
Subject: ALBTELECOM sha won a new tender

ALBTELECOM sha (NIPT: K11234567A) was awarded a tender:
- Tender: Infrastructure maintenance for Q1 2026
- Value: EUR 2,150,000
- Contracting authority: Ministry of Transport
- Award date: 2026-02-07

Shareholders:
- CETEL Group (100%) -> owned by Calik Holding (Turkey)

Legal representatives:
- John Doe (Administrator)

View full details: https://thelbi.al/company/K11234567A/
```

#### Company detail page enhancement

Add a "Tenders" tab to the company detail page showing all procurement wins, sorted by date, with values and contracting authorities.

### Challenges

- **PDF parsing is messy.** APP bulletins aren't always consistently formatted. Tables may span pages, column alignment varies. This is the hardest part technically.
- **NIPT matching.** Some tender records may not include NIPT, only company name. Need fuzzy matching as fallback.
- **Historical data.** APP archives go back years. Starting with current data and backfilling is the right approach (same as company changes).
- **Volume.** Albania processes thousands of tenders per year. Storage and parsing are manageable, but the weekly scrape job needs to be robust.

### Why this is a moat

Once you have 6-12 months of cross-linked company + tender data, no competitor can catch up quickly. The historical cross-references are the product. The data compounds.

---

## Ownership change alerts

### What it is

Users "watch" companies. When the nightly scrape detects a change (new shareholders, removed shareholders, percentage changes, new administrators), the user gets an email.

### Why it matters

- Banks need to know when their clients' ownership changes (KYC/AML requirement)
- Law firms monitoring counterparties in ongoing deals
- Investors tracking portfolio companies

### Technical plan

#### New model: `CompanyWatch`

```python
class CompanyWatch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='watched_companies')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='watchers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'company']
```

#### Integration with existing change detection

The `OwnershipChange` model already records diffs on every nightly scrape. The alert system just needs to:
1. After each nightly scrape completes, check which companies had `OwnershipChange` records created
2. Look up `CompanyWatch` for those companies
3. Send email to each watching user

This is a post-scrape Celery task — the hard part (change detection) is already built.

#### Premium feature

- Free users: can watch 0 companies (or 1-2 as a teaser)
- Professional: watch up to 50 companies
- Business: unlimited watches + API webhook notifications

---

## TODO (prioritized)

### Phase 1 — Launch (get first users)

- [x] **Public landing page** at `/` — explains product, capability cards, pricing summary, signup CTAs
- [ ] **Seed the database** — run full scrape on production server to populate ~5,000 companies
- [x] **Cross-entity person search** — search by person name shows all companies where they appear as shareholder (with %) or administrator. Runs alongside company search.
- [x] **Contact form on pricing page** — "Request Access" form at `/accounts/request-access/` saves to `PricingInquiry` model, visible in Django admin

### Phase 2 — Monetize (get first paying customers)

- [ ] **Ownership change alerts** — user watches companies, gets emailed on changes. Premium feature. The change detection already works; this is just the notification layer.
- [ ] **Invoice generation** — simple PDF proforma invoice with Albanian bank details. Send manually or auto-generate from admin.
- [ ] **Bulk CSV export** — export search results or company lists for KYC workflows

### Phase 3 — Differentiate (the moat)

- [ ] **APP tender integration** — scrape weekly procurement bulletins, parse PDFs, cross-link with company data via NIPT. This is the killer feature.
- [ ] **Tender alerts** — "Company X you're watching just won a tender." Combines company watching with tender data.
- [ ] **Tender search** — search tenders by company, by contracting authority, by value range, by category
- [ ] **Company detail: tenders tab** — show all procurement wins on the company page alongside ownership data

### Phase 4 — Scale

- [ ] **REST API** (DRF) — for banks/law firms that want programmatic access
- [ ] **Ownership chain visualization** — graph UI showing multi-level ownership
- [ ] **Kosovo expansion** — ARBK registry, same language, doubles the market
- [ ] **Webhook alerts** — for API customers who want real-time notifications

### Done

- [x] Company data model with relational shareholders and ownership chains
- [x] Two-phase scraper (listing APIs -> detail pages -> upsert with change detection)
- [x] Full-text search with PostgreSQL SearchVector
- [x] On-demand scraping for unknown NIPTs
- [x] User auth (signup, login, Google OAuth, email verification)
- [x] Search rate limiting (free: 10/day, premium: unlimited)
- [x] Pricing page (Free / Professional EUR 29/mo / Business EUR 79/mo)
- [x] Nightly scrape via Celery Beat (3:00 AM)
- [x] GDPR compliance (data export, account deletion, privacy policy)
- [x] Production deployment (Nginx + Gunicorn + Celery + SSL on DigitalOcean)
- [x] Deploy script (`./deploy.sh`)
- [x] Simplified profile (removed institution/position/bio — irrelevant for this product)

---

## Data strategy

### How much to scrape

**5,000 companies is enough to launch.** These are the companies people do due diligence on — public contractors, banks, concessions, state-owned enterprises. Nobody pays EUR 29/month to look up a sole proprietor barbershop.

Coverage grows organically through on-demand scraping (user searches for unknown NIPT -> background task fetches it).

### Seeding the database (on production server)

```bash
cd /var/www/qkb

# Smallest/highest value first
/var/www/qkb/.venv/bin/python manage.py scrape --categories banka           # 17 banks (~30s)
/var/www/qkb/.venv/bin/python manage.py scrape --categories publike          # 303 state-owned (~8min)
/var/www/qkb/.venv/bin/python manage.py scrape --categories concession       # 288 PPP (~7min)
/var/www/qkb/.venv/bin/python manage.py scrape --categories jobanka          # 40 non-bank (~1min)
/var/www/qkb/.venv/bin/python manage.py scrape --categories companyinvestor  # 61 investors (~2min)
/var/www/qkb/.venv/bin/python manage.py scrape --categories company          # 4,431 contractors (~2hrs)

# After seeding, backfill search vectors
/var/www/qkb/.venv/bin/python manage.py populate_search_vectors
```

Or trigger via Celery (non-blocking):
```bash
/var/www/qkb/.venv/bin/python manage.py shell -c "
from companies.tasks import run_full_scrape_task
result = run_full_scrape_task.delay()
print(f'Task started: {result.id}')
"
```

### Historical changes — start recording now

No way to reconstruct past changes. The `OwnershipChange` model diffs shareholders on every nightly re-scrape. After 6 months you have 6 months of structured change history. This dataset compounds and becomes a moat.

---

## Known issues

### 1. Opencorporates.al will break or block you

**Mitigations in place:**
- `ScrapeLog` tracks errors per run
- Raw HTML stored on each Company for re-parsing
- `REQUEST_DELAY` (1.5s) between requests
- User-Agent identifies the bot

**If HTML changes:** Only `_parse_detail_table()` in `scraper.py` needs updating.
**If they block you:** Scrape QKB directly or use the official gazette.

### 2. Shareholder parsing is ~80-90% accurate

Free-text Albanian with inconsistent formatting. Don't try to make it perfect. Fix specific cases reported by early users via Django admin.

### 3. Search is word-based, not substring-based

Full-text search matches whole words. Typing "komb" won't match "Kombetare" via FTS (but will via the `icontains` fallback, which only triggers when FTS returns nothing).

---

## Pricing model

| Tier | Price | Features | Payment |
|------|-------|----------|---------|
| Free | EUR 0 | 10 searches/day, basic company info | N/A |
| Professional | EUR 29/month | Unlimited search, full details, ownership alerts (planned) | Bank transfer + invoice |
| Business | EUR 79/month | API access, bulk export, tender alerts (planned), priority support | Bank transfer + invoice |

Premium activation: set `user.is_premium = True` in Django admin after payment received.

---

## Scaling beyond Albania

**Near-term:** Kosovo (ARBK registry) — same language, doubles the market.

**Medium-term:** Serbia (APR), North Macedonia (CRRM), Montenegro (CRPS), Bosnia. Sold as "Balkan Company Intelligence" to Vienna/Zurich/London law firms. EUR 200-500/month.

**Long-term:** Central Asia, Caucasus, MENA. Buyers become international due diligence firms (Kroll, Control Risks). They pay local researchers $500/day for manual registry pulls today.

None of that matters until 5 people in Tirana are paying EUR 29/month.

---

## Technical reference

### Stack
- Python 3.13, managed with `uv`
- Django 6.0 + PostgreSQL
- Celery + Redis (broker: `redis://localhost:6379/1`)
- Gunicorn (2 workers on production)
- Nginx reverse proxy with SSL
- httpx + BeautifulSoup + lxml for scraping
- django-environ for settings
- social-auth-app-django for Google OAuth

### Local development
```bash
uv run python manage.py runserver 8001
uv run celery -A config worker -l info
uv run celery -A config beat -l info
```

### Production commands
```bash
# Deploy
cd /var/www/qkb && ./deploy.sh

# Services — status / restart / stop
sudo systemctl status qkb qkb-celery qkb-celerybeat nginx --no-pager
sudo systemctl restart qkb qkb-celery qkb-celerybeat
sudo systemctl stop qkb                 # Stop Gunicorn only
sudo systemctl daemon-reload             # After editing .service files

# Logs — follow or tail
sudo journalctl -u qkb -f
sudo journalctl -u qkb-celery -f
sudo journalctl -u qkb-celerybeat -f
sudo journalctl -u qkb -n 50 --no-pager
sudo journalctl -u qkb-celery -n 50 --no-pager

# Nginx
sudo nginx -t && sudo systemctl reload nginx
ls /etc/nginx/sites-available/
ls /etc/nginx/sites-enabled/

# Edit config files
sudo nano /etc/systemd/system/qkb.service
sudo nano /etc/systemd/system/qkb-celery.service
sudo nano /etc/systemd/system/qkb-celerybeat.service
sudo nano /etc/nginx/sites-available/qkb

# Gunicorn socket check
ls -la /run/gunicorn/

# Django management (on server)
/var/www/qkb/.venv/bin/python manage.py shell
/var/www/qkb/.venv/bin/python manage.py createsuperuser
/var/www/qkb/.venv/bin/python manage.py scrape --categories banka
```

### Project structure
```
qkb/
├── config/                        # Django settings, urls, celery
├── accounts/                      # User auth app
│   ├── models.py                  # User, UserProfile, EmailVerificationLog, ClickTracking
│   ├── views/                     # auth.py, user.py, emails.py, analytics.py, static.py
│   ├── pipeline.py                # Google OAuth pipeline
│   ├── forms.py                   # Signup, login, profile forms
│   └── templates/accounts/
├── companies/                     # Main app
│   ├── models.py                  # Company, Shareholder, LegalRepresentative, OwnershipChange, ScrapeLog
│   ├── scraper.py                 # Two-phase scraper pipeline
│   ├── tasks.py                   # Celery tasks
│   ├── views.py                   # search + company_detail
│   ├── admin.py                   # Admin with inlines
│   └── management/commands/       # scrape, populate_search_vectors
├── templates/                     # base.html, error pages
├── deploy.sh                      # Production deploy script
├── .env                           # Secrets (not committed)
└── pyproject.toml                 # Dependencies
```

### Key files for future work
- **Fix parsing bugs:** `companies/scraper.py` -> `_parse_detail_table()`, `_parse_owner_string()`
- **Add new features:** `companies/views.py` + `companies/urls.py`
- **Add tender integration:** new `tenders/` app, same scraper pattern
- **Add API:** `uv add djangorestframework`, add serializers + viewsets
- **Change search fields:** update `SearchVector(...)` in `scraper.py:upsert_company()`
- **Change rate limits:** edit `FREE_DAILY_LIMIT` in `companies/views.py`
- **Grant premium access:** `user.is_premium = True` in Django admin
- **Configure Google OAuth:** `GOOGLE_OAUTH2_KEY` + `GOOGLE_OAUTH2_SECRET` in `.env`
- **Configure production email:** `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in `.env`
