from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector

from companies.models import Company


class Command(BaseCommand):
    help = 'Backfill search_vector for all existing companies'

    def handle(self, *args, **options):
        count = Company.objects.count()
        self.stdout.write(f'Updating search vectors for {count} companies...')
        Company.objects.update(
            search_vector=SearchVector('name', 'name_latin', 'nipt', 'city')
        )
        self.stdout.write(self.style.SUCCESS(f'Done — {count} companies updated.'))
