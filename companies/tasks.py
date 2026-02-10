import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=60, time_limit=14400, soft_time_limit=13800)
def run_full_scrape_task(self, categories=None, limit=None):
    """
    Full scraping pipeline: collect NIPTs from listings, scrape details, save to DB.
    categories: list of endpoint keys (e.g. ['banka', 'publike']) or None for all.
    limit: max companies to scrape (useful for testing).
    """
    from .scraper import run_full_scrape

    try:
        log = run_full_scrape(categories=categories, limit=limit)
        return {
            'status': log.status,
            'scraped': log.companies_scraped,
            'new': log.companies_new,
            'updated': log.companies_updated,
            'errors_count': len(log.errors),
        }
    except Exception as e:
        logger.error(f"Full scrape task failed: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=10, time_limit=120, soft_time_limit=90)
def scrape_single_nipt_task(self, nipt):
    """
    On-demand scrape for a single company.
    Triggered when a user searches for a NIPT not in the database.
    """
    from .scraper import scrape_single_nipt

    try:
        company = scrape_single_nipt(nipt)
        if company:
            return {'status': 'found', 'nipt': company.nipt, 'name': company.name}
        return {'status': 'not_found', 'nipt': nipt}
    except Exception as e:
        logger.error(f"Single NIPT scrape failed for {nipt}: {e}")
        raise self.retry(exc=e)
