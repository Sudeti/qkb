from django.core.management.base import BaseCommand
from companies.models import Tender, Company


class Command(BaseCommand):
    help = "Re-link tenders whose winner companies have since been scraped into the DB"

    def handle(self, *args, **options):
        unlinked = Tender.objects.filter(
            winner_company__isnull=True,
        ).exclude(winner_nipt='')

        linked_count = 0
        for tender in unlinked:
            try:
                company = Company.objects.get(nipt=tender.winner_nipt)
                tender.winner_company = company
                tender.save(update_fields=['winner_company'])
                linked_count += 1
                self.stdout.write(f"  Linked: {tender.winner_nipt} → {company.name}")
            except Company.DoesNotExist:
                continue

        self.stdout.write(self.style.SUCCESS(
            f"Done. Linked {linked_count} tenders, {unlinked.count()} still unlinked."
        ))
