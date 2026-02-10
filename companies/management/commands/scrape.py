from django.core.management.base import BaseCommand
from companies.scraper import run_full_scrape, LISTING_ENDPOINTS


class Command(BaseCommand):
    help = 'Scrape companies from opencorporates.al'

    def add_arguments(self, parser):
        parser.add_argument(
            '--categories',
            nargs='+',
            choices=list(LISTING_ENDPOINTS.keys()),
            help='Which listing categories to scrape (default: all)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Max number of companies to scrape (for testing)',
        )

    def handle(self, *args, **options):
        categories = options.get('categories')
        limit = options.get('limit')

        if limit:
            self.stdout.write(f"Scraping with limit={limit}")
        if categories:
            self.stdout.write(f"Categories: {', '.join(categories)}")
        else:
            self.stdout.write("Scraping all categories")

        log = run_full_scrape(categories=categories, limit=limit)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {log.companies_scraped} scraped, "
            f"{log.companies_new} new, "
            f"{log.companies_updated} updated, "
            f"{len(log.errors)} errors"
        ))
