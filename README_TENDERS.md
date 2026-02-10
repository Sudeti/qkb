# Tender / Public Procurement Integration

How APP (Agjencia e Prokurimit Publik) procurement data flows into the platform and links to company profiles.

---

## Data source

APP publishes weekly bulletins (PDF) listing awarded public contracts. Each bulletin contains:

- **Contracting authority** — the government entity (ministry, municipality, SH.A)
- **Procurement object** — what was purchased (construction, IT, consulting, etc.)
- **Procedure type** — open, restricted, negotiated, proposal request, small value
- **Fondi limit** — estimated budget in lekë
- **Winner** — company name + NIPT
- **Contract value** — awarded amount in lekë (excl. VAT)
- **Contract date** — when signed
- **Disqualified bidders** — names, NIPTs, and reasons
- **Subcontractors / supporting entities** — names and NIPTs

Bulletins are published at: https://www.app.gov.al/buletini-i-prokurimit-publik/

---

## Data model

The `Tender` model lives in `companies/models.py` and stores one awarded contract per row.

### Key fields

| Field | Type | Description |
|-------|------|-------------|
| `bulletin_number` | CharField | APP bulletin ref (e.g., "Nr. 5") |
| `bulletin_date` | DateField | Publication date of the bulletin |
| `reference_number` | CharField | Procedure ref (REF-xxxxx-xx-xx-xx) |
| `authority_name` | CharField | Contracting authority name |
| `authority_type` | CharField | e.g., SH.A, Ministry, Municipality |
| `title` | TextField | Procurement object description |
| `procedure_type` | CharField | open / restricted / negotiated / proposal / consultancy / small_value / design_contest / other |
| `status` | CharField | awarded / cancelled / appealed |
| `estimated_value` | Decimal | Fondi limit (lekë) |
| `contract_value` | Decimal | Contract value (lekë, excl. VAT) |
| `winner_name` | CharField | Winner name as listed in bulletin |
| `winner_nipt` | CharField | Winner NIPT from bulletin |
| `winner_company` | FK → Company | Auto-linked by NIPT (see below) |
| `contract_date` | DateField | Date contract was signed |
| `num_bidders` | Integer | Number of bidders |
| `disqualified_bidders` | JSON | `[{name, nipt, reason}]` |
| `subcontractors` | JSON | `[{name, nipt, value}]` |

### Indexes

- `winner_nipt` — fast lookup for company profile pages
- `authority_name` — filter by contracting authority
- `bulletin_date` — browse by publication date
- `reference_number` — deduplicate on import

---

## Auto-linking workflow

When a tender is saved, the system automatically tries to connect `winner_nipt` to a Company record:

```
Tender saved with winner_nipt
        │
        ▼
  Company exists in DB?
   ┌─────┴─────┐
   Yes         No
   │            │
   ▼            ▼
 Link FK    Fire Celery task:
             scrape_single_nipt_task(nipt)
             (scrapes from opencorporates.al)
```

**If the company IS in the database:**
- `winner_company` FK is set immediately
- Tender appears on the company detail page under "Public Procurement"

**If the company is NOT in the database:**
- Tender saves with `winner_company = NULL` (name and NIPT are still stored)
- A Celery task fires to scrape that company from opencorporates.al
- After the scrape completes (~30 seconds), run `link_tenders` to connect them

---

## Manual data entry (current workflow)

Until automated bulletin parsing is built, enter tenders via Django admin:

1. Go to **Admin → Companies → Tenders → Add Tender**
2. Fill in fields from the APP bulletin:
   - Bulletin number and date
   - Authority name
   - Title (procurement object)
   - Procedure type
   - Estimated value and contract value (in lekë, no dots/commas — just the number)
   - Winner name and NIPT
   - Contract date
3. Click **Save**
4. If the company was already in the DB → linked automatically
5. If not → scrape fires in background. Run `link_tenders` after a minute

### Entering disqualified bidders

The `disqualified_bidders` field accepts JSON. Format:

```json
[
  {"name": "COMPANY NAME Shpk", "nipt": "L12345678A", "reason": "Nuk plotëson kriterin e kapacitetit teknik"},
  {"name": "OTHER COMPANY Shpk", "nipt": "M98765432B", "reason": "Ofertë anomalisht e ulët"}
]
```

### Entering subcontractors

```json
[
  {"name": "SUB COMPANY Shpk", "nipt": "K11111111A", "value": 5000000}
]
```

---

## Management commands

### `link_tenders` — re-link unlinked tenders

After companies get scraped into the DB (either via on-demand scrape or nightly full scrape), run this to connect any tenders that were waiting:

```bash
uv run python manage.py link_tenders
```

Output:
```
  Linked: M01323012A → LAVIVA TECHNOLOGIES Shpk
  Linked: L91234567A → SOME OTHER COMPANY Shpk
Done. Linked 2 tenders, 0 still unlinked.
```

Run this:
- After entering a batch of tenders (wait ~1 min for scrapes to finish)
- After the nightly scrape completes
- Anytime — it's idempotent and fast

---

## Where tenders appear in the product

### Company detail page (`/company/<nipt>/`)

If a company has won any tenders, a **"Public Procurement"** section appears showing:
- Tender title
- Contract value in lekë
- Contracting authority
- Procedure type
- Contract date

### Admin

Full CRUD at **Admin → Companies → Tenders** with:
- List view: winner, authority, title, value, procedure type, status, date
- Filters: status, procedure type, bulletin date
- Search: winner name/NIPT, authority, title, reference number
- Date hierarchy by bulletin date

---

## Mapping APP bulletin fields to model fields

When reading a bulletin entry like this:

```
Autoriteti kontraktor:  SH.A ALBPETROL
Objekti i prokurimit:   Blerje materiale ndërtimi
Fondi limit:            16,400,000 lekë pa TVSH
Ofertuesi fitues:       "LAVIVA TECHNOLOGIES" Shpk, NIPT M01323012A
Vlera e kontratës:      14,200,000 lekë pa TVSH
Data e lidhjes:         30.01.2026
Lloji i procedurës:     Kërkesë për Propozim
Nr. referencës:         REF-12345-01-30-2026
```

Map it to:

| Bulletin field | Model field | Value |
|---------------|-------------|-------|
| Autoriteti kontraktor | `authority_name` | SH.A ALBPETROL |
| — | `authority_type` | SH.A |
| Objekti i prokurimit | `title` | Blerje materiale ndërtimi |
| Fondi limit | `estimated_value` | 16400000 |
| Ofertuesi fitues (name) | `winner_name` | LAVIVA TECHNOLOGIES Shpk |
| Ofertuesi fitues (NIPT) | `winner_nipt` | M01323012A |
| Vlera e kontratës | `contract_value` | 14200000 |
| Data e lidhjes | `contract_date` | 2026-01-30 |
| Lloji i procedurës | `procedure_type` | `proposal` |
| Nr. referencës | `reference_number` | REF-12345-01-30-2026 |

### Procedure type mapping

| Albanian | `procedure_type` value |
|----------|----------------------|
| Procedurë e Hapur | `open` |
| Procedurë e Kufizuar | `restricted` |
| Procedurë me Negocim | `negotiated` |
| Kërkesë për Propozim | `proposal` |
| Shërbim Konsulence | `consultancy` |
| Vlerë e Vogël | `small_value` |
| Konkurs Projektimi | `design_contest` |

---

## Future: automated bulletin parsing

The APP bulletin PDFs follow a semi-structured format. An automated parser would:

1. Download the weekly PDF from app.gov.al
2. Extract text (PyPDF2 / pdfplumber)
3. Split into individual tender entries (by "Autoriteti kontraktor" headers)
4. Regex-extract NIPTs (`[A-Z]\d{7,9}[A-Z]`), values (`[\d,.]+ lekë`), dates, authority names
5. Map to Tender model fields
6. Deduplicate by `reference_number`
7. Save → auto-link triggers scrape for unknown companies

This would be a management command: `uv run python manage.py import_bulletin bulletin.pdf`

Not built yet — manual entry via admin covers the initial dataset.
