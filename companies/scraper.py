"""
QKB Scraper — Two-phase pipeline:
  Phase 1: Collect NIPTs from opencorporates.al listing APIs
  Phase 2: Scrape detail pages for each NIPT
"""
import logging
import time
import html as html_module
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from django.utils import timezone

from .models import Company, Shareholder, LegalRepresentative, OwnershipChange, ScrapeLog

logger = logging.getLogger(__name__)

BASE_URL = "https://opencorporates.al"
REQUEST_DELAY = 1.5  # seconds between requests — be polite
REQUEST_TIMEOUT = 30

# Listing endpoints and their total record counts (as of Feb 2026)
LISTING_ENDPOINTS = {
    'company': '/sq/company/any',       # ~4,431 public contractors
    'publike': '/sq/publike/any',        # ~303 state-owned
    'concession': '/sq/concession/any',  # ~288 PPP/concessions
    'banka': '/sq/banka/any',            # ~17 banks
    'jobanka': '/sq/jobanka/any',        # ~40 non-bank financial
    'companyinvestor': '/sq/companyinvestor/any',  # ~61 strategic investors
}

LEGAL_FORM_MAP = {
    'shoqëri me përgjegjësi të kufizuar': 'shpk',
    'shoqëri aksionare': 'sha',
    'shoqëri aksionare sh.a': 'sha',
    'person fizik': 'pf',
    'degë e shoqërisë së huaj': 'deg',
}


def _map_legal_form(value):
    cleaned = value.lower().strip()
    # Try exact match first
    if cleaned in LEGAL_FORM_MAP:
        return LEGAL_FORM_MAP[cleaned]
    # Try substring match
    for key, code in LEGAL_FORM_MAP.items():
        if key in cleaned:
            return code
    return 'other'

STATUS_MAP = {
    'aktiv': 'active',
    'pezulluar': 'suspended',
    'çregjistruar': 'dissolved',
    'falimentuar': 'bankruptcy',
    'në likuidim': 'in_liquidation',
}


def get_client():
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={
            'User-Agent': 'QKBIntelligence/1.0 (research; contact@qkb.al)',
            'Accept': 'application/json, text/html',
        },
        follow_redirects=True,
    )


# ──────────────────────────────────────────────
# Phase 1: Collect NIPTs from listing APIs
# ──────────────────────────────────────────────

def collect_nipts_from_listings(categories=None):
    """
    Hit listing APIs and return a deduplicated set of NIPTs.
    categories: list of keys from LISTING_ENDPOINTS, or None for all.
    """
    if categories is None:
        categories = list(LISTING_ENDPOINTS.keys())

    all_nipts = set()

    with get_client() as client:
        for category in categories:
            endpoint = LISTING_ENDPOINTS.get(category)
            if not endpoint:
                logger.warning(f"Unknown category: {category}")
                continue

            url = f"{BASE_URL}{endpoint}"
            logger.info(f"Fetching {category} listing from {url}")

            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

                records = data.get('data', [])
                total = data.get('recordsTotal', 0)
                logger.info(f"  {category}: {len(records)} records fetched (total: {total})")

                for record in records:
                    nipt = _clean_nipt(record.get('NIPT', ''))
                    if nipt:
                        all_nipts.add(nipt)

                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.error(f"  Failed to fetch {category}: {e}")

    logger.info(f"Collected {len(all_nipts)} unique NIPTs")
    return all_nipts


def _clean_nipt(raw):
    """Extract plain NIPT from possibly HTML-wrapped value."""
    if '<' in raw:
        soup = BeautifulSoup(raw, 'html.parser')
        text = soup.get_text(strip=True)
    else:
        text = raw.strip()
    return html_module.unescape(text)


# ──────────────────────────────────────────────
# Phase 2: Scrape detail page for a single NIPT
# ──────────────────────────────────────────────

def scrape_company_detail(nipt, client=None):
    """
    Fetch and parse the detail page for a single company.
    Returns a dict of parsed data, or None on failure.
    """
    own_client = client is None
    if own_client:
        client = get_client()

    url = f"{BASE_URL}/en/nipt/{nipt}"

    try:
        resp = client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        data = {
            'nipt': nipt,
            'source_url': url,
            'raw_html': resp.text,
        }

        # Company name from <title> tag (h1 contains site name)
        title = soup.find('title')
        if title:
            data['name'] = title.get_text(strip=True)

        # Parse the main info table
        _parse_detail_table(soup, data)

        return data

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"Company not found: {nipt}")
        else:
            logger.error(f"HTTP error for {nipt}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to scrape {nipt}: {e}")
        return None
    finally:
        if own_client:
            client.close()


def _parse_detail_table(soup, data):
    """
    Parse the main info table on opencorporates.al detail pages.
    Structure: <table> with <tr> rows, each having 2 <td> cells (label, value).
    """
    tables = soup.find_all('table')
    if not tables:
        return

    # Main info is in the first table
    main_table = tables[0]
    fields = {}

    for row in main_table.find_all('tr'):
        th = row.find('th')
        td = row.find('td')
        if th and td:
            label = th.get_text(strip=True).lower().rstrip(':')
            value = td.get_text(strip=True)
            if label and value:
                fields[label] = value

    # Map parsed fields to model fields
    if 'legal form' in fields or 'forma ligjore' in fields:
        data['legal_form'] = _map_legal_form(fields.get('legal form', fields.get('forma ligjore', '')))

    if 'status' in fields or 'statusi' in fields:
        data['status'] = _map_status(fields.get('status', fields.get('statusi', '')))

    if 'foundation year' in fields or 'data e themelimit' in fields:
        data['registration_date'] = _parse_date(fields.get('foundation year', fields.get('data e themelimit', '')))

    if 'initial capital' in fields or 'kapitali fillestar' in fields:
        data['capital'] = _parse_capital(fields.get('initial capital', fields.get('kapitali fillestar', '')))

    if 'district' in fields or 'rrethi' in fields:
        city = fields.get('district', fields.get('rrethi', ''))
        # Take first district if multiple listed
        data['city'] = city.split(',')[0].strip() if city else ''

    if 'address' in fields or 'adresa' in fields:
        data['address'] = fields.get('address', fields.get('adresa', ''))

    if 'scope' in fields or 'objekti' in fields:
        data['nace_description'] = fields.get('scope', fields.get('objekti', ''))[:500]

    # Parse administrators from semicolon-separated string
    admin_str = fields.get('administrators', fields.get('administratori', ''))
    data['administrators'] = []
    if admin_str:
        for name in _split_names(admin_str):
            data['administrators'].append({'full_name': name, 'role': 'Administrator'})

    # Parse board members
    board_str = fields.get('board members', fields.get('anëtarë të bordit', ''))
    if board_str:
        for name in _split_names(board_str):
            data['administrators'].append({'full_name': name, 'role': 'Board Member'})

    # Parse shareholders from "Parent Company / Owner" table field
    owner_str = fields.get('parent company / owner', fields.get('shoqëria mëmë/ ortaku', ''))
    data['shareholders'] = _parse_owner_string(owner_str)

    # If no shareholders from table, try the <ul> "Shareholders/Ownership" section
    if not data['shareholders']:
        data['shareholders'] = _parse_shareholders_list(soup)


# ──────────────────────────────────────────────
# Phase 3: Save parsed data to database
# ──────────────────────────────────────────────

def upsert_company(data):
    """
    Create or update a Company record from scraped data.
    Returns (company, created, changed) tuple.
    """
    nipt = data['nipt']
    now = timezone.now()

    defaults = {
        'name': data.get('name', ''),
        'legal_form': data.get('legal_form', 'other'),
        'status': data.get('status', 'active'),
        'registration_date': data.get('registration_date'),
        'capital': data.get('capital'),
        'address': data.get('address', ''),
        'city': data.get('city', ''),
        'raw_pdf_text': data.get('raw_html', '')[:50000],  # cap storage
        'source_url': data.get('source_url', ''),
        'last_scraped': now,
    }

    # Filter out None values to avoid overwriting good data with null
    defaults = {k: v for k, v in defaults.items() if v is not None and v != ''}

    company, created = Company.objects.update_or_create(
        nipt=nipt,
        defaults=defaults,
    )

    # Update search vector
    from django.contrib.postgres.search import SearchVector
    Company.objects.filter(pk=company.pk).update(
        search_vector=SearchVector('name', 'name_latin', 'nipt', 'city')
    )

    # Detect ownership changes by diffing shareholders
    changed = _sync_shareholders(company, data.get('shareholders', []))

    # Sync administrators
    _sync_administrators(company, data.get('administrators', []))

    return company, created, changed


def _parse_owner_string(owner_str):
    """
    Parse the 'Parent Company / Owner' field.

    Common formats:
    1. Single owner: '"Raiffeisen SEE Region Holding GmbH", shoqëri e themeluar...'
    2. Multiple owners with Roman numerals: 'I.\t"ARMAAR GROUP", shoqëri... II.\t"E D R O", shoqëri...'
    3. Simple name list: 'Edmond Leka dhe Niko Leka'
    """
    import re
    shareholders = []
    if not owner_str:
        return shareholders

    # Split on Roman numeral prefixes (I., II., III., IV., V., VI., VII., VIII., IX., X., etc.)
    # These appear as "I.\t" or "I. " at the start of each shareholder entry
    # Use explicit list to avoid partial matches within text
    entries = re.split(
        r'(?:^|[\s\n])(?:VIII|VII|VI|IV|IX|III|II|XI|XII|X|V|I)\.\s*\t?\s*',
        owner_str
    )

    # If no Roman numerals found, treat the whole string as one entry
    if len(entries) <= 1:
        entries = [owner_str]

    for entry in entries:
        entry = entry.strip()
        if not entry or len(entry) < 3:
            continue

        # Extract quoted company name if present: "Company Name"
        quoted = re.match(r'["\u201c]([^"\u201d]+)["\u201d]', entry)

        if quoted:
            name = quoted.group(1).strip()
        else:
            # No quotes — take text up to first comma or descriptive phrase
            # e.g., "OTP Bank Nyrt, një shoqëri..." -> "OTP Bank Nyrt"
            name_match = re.match(r'^([^,]+)', entry)
            name = name_match.group(1).strip() if name_match else entry[:100]

        # Skip noise
        if not name or name.lower().startswith(('nuk ka', 'no data', 'sipas')):
            continue

        # Detect company vs individual
        company_markers = ['SH.A', 'SHPK', 'SH.P.K', 'LLC', 'GMBH', 'SRL', 'LTD', 'INC',
                          'S.R.L', 'S.P.A', 'NYRT', 'B.V', 'A.G', 'HOLDING', 'BANK',
                          'GROUP', 'CORP', 'shoqëri', 'kompani']
        full_text = (name + ' ' + entry[:200]).upper()
        is_company = any(marker.upper() in full_text for marker in company_markers)

        sh = {
            'full_name': name[:300],
            'shareholder_type': 'company' if is_company else 'individual',
        }

        # Try to extract percentage
        pct = _parse_percentage(entry)
        if pct is not None:
            sh['ownership_pct'] = pct

        # Try to extract NIPT of the parent company
        nipt_match = re.search(r'NIPT\s+([A-Z]\d{7,9}[A-Z])', entry)
        if nipt_match:
            sh['parent_nipt'] = nipt_match.group(1)

        shareholders.append(sh)

    return shareholders


def _parse_shareholders_list(soup):
    """
    Parse shareholders from the <ul class="list-group"> section
    under the "Shareholders/Ownership" heading.

    Each <li> contains an <a> with text like "Jolanda Trebicka - 100%"
    or "SOME COMPANY SH.A - 51%".
    """
    import re
    shareholders = []

    # Find the heading — span.string is None when tag has mixed content,
    # so match on get_text() instead
    sh_heading = soup.find(
        'span', string=lambda t: t and 'Shareholders' in t
    )
    if not sh_heading:
        # Fallback: search all spans by text content
        for span in soup.find_all('span'):
            if 'Shareholders' in span.get_text() or 'Ortakë' in span.get_text():
                sh_heading = span
                break
    if not sh_heading:
        return shareholders

    # Walk up to the title-divider or parent div, then find the next <ul>
    parent_div = sh_heading.find_parent('div', class_='title-divider')
    if not parent_div:
        parent_div = sh_heading.find_parent('div')

    ul = parent_div.find_next('ul', class_='list-group')
    if not ul:
        return shareholders

    for li in ul.find_all('li', class_='list-group-item'):
        a_tag = li.find('a')
        text = a_tag.get_text(strip=True) if a_tag else li.get_text(strip=True)
        if not text or len(text) < 2:
            continue

        # Split on " - " to separate name from percentage
        # e.g. "Jolanda Trebicka - 100%"
        parts = text.rsplit(' - ', 1)
        name = parts[0].strip()

        if not name or name.lower().startswith(('nuk ka', 'no data')):
            continue

        pct = None
        if len(parts) > 1:
            pct = _parse_percentage(parts[1])

        company_markers = ['SH.A', 'SHPK', 'SH.P.K', 'LLC', 'GMBH', 'SRL', 'LTD', 'INC',
                          'S.R.L', 'S.P.A', 'NYRT', 'B.V', 'A.G', 'HOLDING', 'BANK',
                          'GROUP', 'CORP']
        is_company = any(marker in name.upper() for marker in company_markers)

        sh = {
            'full_name': name[:300],
            'shareholder_type': 'company' if is_company else 'individual',
        }
        if pct is not None:
            sh['ownership_pct'] = pct

        # Try to extract NIPT from the href
        if a_tag and a_tag.get('href'):
            nipt_match = re.search(r'([A-Z]\d{7,9}[A-Z])', a_tag.get('href', ''))
            if nipt_match:
                sh['parent_nipt'] = nipt_match.group(1)

        shareholders.append(sh)

    return shareholders


def _sync_shareholders(company, new_shareholders):
    """
    Compare current shareholders with scraped data.
    If changed, record an OwnershipChange and update.
    Returns True if ownership changed.
    """
    if not new_shareholders:
        return False

    current = list(
        company.shareholders.values_list('full_name', 'ownership_pct')
    )
    incoming = [
        (s['full_name'], s.get('ownership_pct'))
        for s in new_shareholders
    ]

    # Normalize for comparison
    current_set = {(n, str(p) if p else None) for n, p in current}
    incoming_set = {(n, str(p) if p else None) for n, p in incoming}

    if current_set == incoming_set:
        return False

    # Record the change
    if current:  # only log change if we had previous data
        OwnershipChange.objects.create(
            company=company,
            change_date=timezone.now().date(),
            description="Ownership change detected during scrape",
            old_shareholders=[
                {'name': n, 'pct': str(p) if p else None}
                for n, p in current
            ],
            new_shareholders=[
                {'name': s['full_name'], 'pct': str(s.get('ownership_pct', ''))}
                for s in new_shareholders
            ],
        )

    # Replace shareholders
    company.shareholders.all().delete()
    for s in new_shareholders:
        # Try to link parent_company FK if we have their NIPT
        parent_company = None
        parent_nipt = s.get('parent_nipt')
        if parent_nipt:
            parent_company = Company.objects.filter(nipt=parent_nipt).first()

        Shareholder.objects.create(
            company=company,
            shareholder_type=s.get('shareholder_type', 'individual'),
            full_name=s.get('full_name', ''),
            parent_company=parent_company,
            parent_company_name=s.get('full_name', '') if s.get('shareholder_type') == 'company' else '',
            ownership_pct=s.get('ownership_pct'),
        )

    return True


def _sync_administrators(company, new_admins):
    """Replace administrators with latest scraped data."""
    if not new_admins:
        return

    company.representatives.all().delete()
    for admin in new_admins:
        LegalRepresentative.objects.create(
            company=company,
            full_name=admin.get('full_name', ''),
            role=admin.get('role', 'Administrator'),
        )


# ──────────────────────────────────────────────
# Full pipeline: collect + scrape + save
# ──────────────────────────────────────────────

def run_full_scrape(categories=None, limit=None):
    """
    Run the complete scraping pipeline.
    categories: which listing endpoints to pull NIPTs from
    limit: max companies to scrape (for testing)
    """
    log = ScrapeLog.objects.create(status='running')
    scraped = 0
    new_count = 0
    updated_count = 0
    errors = []

    try:
        # Phase 1: Collect NIPTs
        nipts = collect_nipts_from_listings(categories)
        nipt_list = sorted(nipts)

        if limit:
            nipt_list = nipt_list[:limit]

        logger.info(f"Starting detail scrape for {len(nipt_list)} companies")

        # Phase 2 + 3: Scrape and save each
        with get_client() as client:
            for i, nipt in enumerate(nipt_list):
                try:
                    data = scrape_company_detail(nipt, client=client)
                    if data:
                        company, created, changed = upsert_company(data)
                        scraped += 1
                        if created:
                            new_count += 1
                        else:
                            updated_count += 1

                        if (i + 1) % 50 == 0:
                            logger.info(f"  Progress: {i + 1}/{len(nipt_list)} scraped")
                            # Update log periodically
                            log.companies_scraped = scraped
                            log.companies_new = new_count
                            log.companies_updated = updated_count
                            log.save()

                    time.sleep(REQUEST_DELAY)

                except Exception as e:
                    error_msg = f"Error scraping {nipt}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

        log.companies_scraped = scraped
        log.companies_new = new_count
        log.companies_updated = updated_count
        log.errors = errors
        log.status = 'completed'
        log.completed_at = timezone.now()
        log.save()

        logger.info(f"Scrape complete: {scraped} scraped, {new_count} new, {updated_count} updated, {len(errors)} errors")

    except Exception as e:
        logger.error(f"Full scrape failed: {e}")
        log.status = 'failed'
        log.errors = errors + [str(e)]
        log.completed_at = timezone.now()
        log.save()

    return log


def scrape_single_nipt(nipt):
    """
    On-demand scrape for a single NIPT.
    Used when a user searches for a company not yet in the DB.
    """
    data = scrape_company_detail(nipt)
    if data:
        company, created, changed = upsert_company(data)
        return company
    return None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _split_names(name_str):
    """
    Split a string of names separated by semicolons or commas.
    Semicolons take priority. If no semicolons, fall back to commas.
    Returns list of cleaned name strings.
    """
    if ';' in name_str:
        parts = name_str.split(';')
    else:
        parts = name_str.split(',')

    names = []
    for part in parts:
        name = part.strip()
        if name and len(name) > 1:
            names.append(name)
    return names


def _map_status(value):
    cleaned = value.lower().strip()
    if cleaned in STATUS_MAP:
        return STATUS_MAP[cleaned]
    for key, code in STATUS_MAP.items():
        if key in cleaned:
            return code
    return 'active'


def _parse_date(value):
    """Try to parse a date from various formats."""
    import re
    from datetime import date

    # Try DD/MM/YYYY or DD.MM.YYYY
    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', value)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # Try YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Try "Month DD, YYYY" or "DD Month YYYY"
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'janar': 1, 'shkurt': 2, 'mars': 3, 'prill': 4,
        'maj': 5, 'qershor': 6, 'korrik': 7, 'gusht': 8,
        'shtator': 9, 'tetor': 10, 'nëntor': 11, 'dhjetor': 12,
    }
    for month_name, month_num in months.items():
        if month_name in value.lower():
            nums = re.findall(r'\d+', value)
            if len(nums) >= 2:
                day = int(nums[0]) if int(nums[0]) <= 31 else int(nums[1])
                year = int(nums[-1])
                try:
                    return date(year, month_num, day)
                except ValueError:
                    pass

    return None


def _parse_capital(value):
    """
    Extract numeric capital value.
    Albanian format: "14 178 593 030,00" (spaces as thousands sep, comma as decimal).
    """
    import re
    # Remove everything except digits and comma
    cleaned = re.sub(r'[^\d,]', '', value)
    # Replace comma with dot for decimal
    cleaned = cleaned.replace(',', '.')
    if cleaned:
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            pass
    return None


def _parse_percentage(value):
    """Extract percentage from text like '51%' or '51.5 %'."""
    import re
    m = re.search(r'([\d.]+)\s*%', value)
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            pass
    return None
