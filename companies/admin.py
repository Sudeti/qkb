from django.contrib import admin
from .models import Company, Shareholder, LegalRepresentative, OwnershipChange, Tender, ScrapeLog


class ShareholderInline(admin.TabularInline):
    model = Shareholder
    fk_name = 'company'
    extra = 0
    fields = ['shareholder_type', 'full_name', 'parent_company_name', 'ownership_pct', 'effective_date']


class LegalRepresentativeInline(admin.TabularInline):
    model = LegalRepresentative
    extra = 0


class OwnershipChangeInline(admin.TabularInline):
    model = OwnershipChange
    extra = 0
    fields = ['change_date', 'description']


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['nipt', 'name', 'legal_form', 'status', 'city', 'registration_date', 'last_scraped']
    list_filter = ['status', 'legal_form', 'city']
    search_fields = ['nipt', 'name', 'name_latin']
    readonly_fields = ['created_at', 'updated_at', 'last_scraped', 'raw_pdf_text']
    inlines = [ShareholderInline, LegalRepresentativeInline, OwnershipChangeInline]

    fieldsets = (
        ('Identity', {
            'fields': ('nipt', 'name', 'name_latin', 'legal_form', 'status')
        }),
        ('Classification', {
            'fields': ('nace_code', 'nace_description')
        }),
        ('Registration', {
            'fields': ('registration_date', 'capital', 'capital_currency')
        }),
        ('Address', {
            'fields': ('address', 'city', 'municipality')
        }),
        ('Scraper Data', {
            'classes': ('collapse',),
            'fields': ('raw_pdf_text', 'source_url', 'last_scraped', 'created_at', 'updated_at')
        }),
    )


@admin.register(Shareholder)
class ShareholderAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'company', 'shareholder_type', 'ownership_pct', 'effective_date']
    list_filter = ['shareholder_type']
    search_fields = ['full_name', 'parent_company_name', 'company__name']
    raw_id_fields = ['company', 'parent_company']


@admin.register(LegalRepresentative)
class LegalRepresentativeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'role', 'company', 'appointed_date']
    search_fields = ['full_name', 'company__name']
    raw_id_fields = ['company']


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ['winner_name', 'authority_name', 'title_short', 'contract_value_fmt', 'procedure_type', 'status', 'bulletin_date']
    list_filter = ['status', 'procedure_type', 'bulletin_date']
    search_fields = ['winner_name', 'winner_nipt', 'authority_name', 'title', 'reference_number']
    raw_id_fields = ['winner_company']
    date_hierarchy = 'bulletin_date'
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Bulletin', {
            'fields': ('bulletin_number', 'bulletin_date', 'reference_number')
        }),
        ('Contracting Authority', {
            'fields': ('authority_name', 'authority_type')
        }),
        ('Procurement', {
            'fields': ('title', 'procedure_type', 'status')
        }),
        ('Financials', {
            'fields': ('estimated_value', 'contract_value')
        }),
        ('Winner', {
            'fields': ('winner_name', 'winner_nipt', 'winner_company')
        }),
        ('Details', {
            'fields': ('contract_date', 'num_bidders', 'disqualified_bidders', 'subcontractors')
        }),
        ('Metadata', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        }),
    )

    @admin.display(description='Title')
    def title_short(self, obj):
        return obj.title[:60] + '...' if len(obj.title) > 60 else obj.title

    @admin.display(description='Value (lekë)')
    def contract_value_fmt(self, obj):
        if obj.contract_value:
            return f"{obj.contract_value:,.0f}"
        return '-'


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = ['started_at', 'status', 'companies_scraped', 'companies_new', 'companies_updated']
    list_filter = ['status']
    readonly_fields = ['started_at', 'completed_at', 'companies_scraped', 'companies_updated', 'companies_new', 'errors']
