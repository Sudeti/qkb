from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex


class Company(models.Model):
    """
    Core entity scraped from QKB (Qendra Kombëtare e Biznesit).
    Each record represents one registered business in Albania.
    """
    LEGAL_FORMS = [
        ('shpk', 'Sh.P.K. (LLC)'),
        ('sha', 'Sh.A. (Joint Stock)'),
        ('pf', 'Person Fizik (Sole Proprietor)'),
        ('deg', 'Degë e Shoqërisë së Huaj (Foreign Branch)'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Aktiv'),
        ('suspended', 'Pezulluar'),
        ('dissolved', 'Çregjistruar'),
        ('bankruptcy', 'Falimentuar'),
        ('in_liquidation', 'Në Likuidim'),
    ]

    nipt = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="NIPT/NUIS - unique tax identification number"
    )
    name = models.CharField(max_length=500, db_index=True)
    name_latin = models.CharField(max_length=500, blank=True)

    legal_form = models.CharField(max_length=10, choices=LEGAL_FORMS, default='shpk')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    nace_code = models.CharField(max_length=10, blank=True, help_text="NACE activity code")
    nace_description = models.TextField(blank=True)

    registration_date = models.DateField(null=True, blank=True)
    capital = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    capital_currency = models.CharField(max_length=5, default='ALL')

    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    municipality = models.CharField(max_length=100, blank=True)

    search_vector = SearchVectorField(null=True)

    raw_pdf_text = models.TextField(blank=True, help_text="Raw extracted text from QKB PDF")
    source_url = models.URLField(blank=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ['name']
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['status', 'city']),
            models.Index(fields=['legal_form']),
            models.Index(fields=['registration_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.nipt})"


class Shareholder(models.Model):
    SHAREHOLDER_TYPES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='shareholders')
    shareholder_type = models.CharField(max_length=12, choices=SHAREHOLDER_TYPES)

    full_name = models.CharField(max_length=300, blank=True, db_index=True)

    parent_company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subsidiaries',
        help_text="If shareholder is another company in our DB"
    )
    parent_company_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Name of parent company (even if not yet in our DB)"
    )

    ownership_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Ownership percentage"
    )
    share_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    effective_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['full_name']),
            models.Index(fields=['company', 'shareholder_type']),
        ]

    def __str__(self):
        name = self.full_name or self.parent_company_name or "Unknown"
        pct = f" ({self.ownership_pct}%)" if self.ownership_pct else ""
        return f"{name}{pct} -> {self.company.name}"


class LegalRepresentative(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='representatives')
    full_name = models.CharField(max_length=300, db_index=True)
    role = models.CharField(max_length=100, default='Administrator')
    appointed_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['full_name']),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.role}) @ {self.company.name}"


class OwnershipChange(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ownership_changes')
    change_date = models.DateField()
    description = models.TextField()
    old_shareholders = models.JSONField(default=list)
    new_shareholders = models.JSONField(default=list)
    source = models.CharField(max_length=100, default='qkb_scrape')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-change_date']
        indexes = [
            models.Index(fields=['company', 'change_date']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.change_date}"


class ScrapeLog(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    companies_scraped = models.IntegerField(default=0)
    companies_updated = models.IntegerField(default=0)
    companies_new = models.IntegerField(default=0)
    errors = models.JSONField(default=list)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Scrape {self.started_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"
