import re
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q
from .models import Company, Shareholder, LegalRepresentative


# Albanian NIPT pattern: letter + digits + letter (e.g., L91234567A)
NIPT_PATTERN = re.compile(r'^[A-Za-z]\d{7,9}[A-Za-z]$')

FREE_DAILY_LIMIT = 10


def _check_and_increment_search(user):
    """
    Check if user can search. Reset counter if date changed.
    Returns (allowed, searches_remaining).
    Premium and superusers are unlimited.
    """
    if user.is_premium or user.is_superuser:
        return True, None

    today = date.today()
    if user.searches_reset_date != today:
        user.searches_today = 0
        user.searches_reset_date = today

    if user.searches_today >= FREE_DAILY_LIMIT:
        return False, 0

    user.searches_today += 1
    user.save(update_fields=['searches_today', 'searches_reset_date'])
    return True, FREE_DAILY_LIMIT - user.searches_today


def landing(request):
    if request.user.is_authenticated:
        return redirect('companies:search')
    return render(request, 'companies/landing.html')


@login_required
def search(request):
    query = request.GET.get('q', '').strip()
    results = []
    person_results = []
    on_demand_triggered = False
    limit_reached = False
    searches_remaining = None
    is_premium = request.user.is_premium or request.user.is_superuser

    if query:
        # Check rate limit
        allowed, searches_remaining = _check_and_increment_search(request.user)
        if not allowed:
            limit_reached = True
        else:
            # Try NIPT exact match first
            nipt_match = Company.objects.filter(nipt__iexact=query).first()
            if nipt_match:
                results = [nipt_match]
            else:
                # Full-text search on search_vector
                search_query = SearchQuery(query, search_type='plain')
                fts_results = Company.objects.filter(
                    search_vector=search_query
                ).annotate(
                    rank=SearchRank('search_vector', search_query)
                ).order_by('-rank')[:50]

                if fts_results.exists():
                    results = fts_results
                else:
                    # Fallback to icontains on company name
                    results = Company.objects.filter(
                        Q(name__icontains=query) |
                        Q(name_latin__icontains=query)
                    ).distinct()[:50]

                # If query looks like a NIPT and no results, trigger on-demand scrape
                if not results and NIPT_PATTERN.match(query):
                    from .tasks import scrape_single_nipt_task
                    scrape_single_nipt_task.delay(query.upper())
                    on_demand_triggered = True

            # Person search — always runs alongside company search
            if not NIPT_PATTERN.match(query):
                company_nipts = set()
                if results:
                    company_nipts = {c.nipt for c in results}

                seen = set()
                shareholder_matches = Shareholder.objects.filter(
                    full_name__icontains=query
                ).select_related('company')[:50]
                for s in shareholder_matches:
                    key = (s.company.nipt, s.full_name)
                    if key not in seen:
                        seen.add(key)
                        pct = f"{s.ownership_pct:g}%" if s.ownership_pct else ''
                        person_results.append({
                            'company': s.company,
                            'person_name': s.full_name,
                            'role': 'Shareholder',
                            'detail': pct,
                            'in_company_results': s.company.nipt in company_nipts,
                        })

                rep_matches = LegalRepresentative.objects.filter(
                    full_name__icontains=query
                ).select_related('company')[:50]
                for r in rep_matches:
                    key = (r.company.nipt, r.full_name)
                    if key not in seen:
                        seen.add(key)
                        person_results.append({
                            'company': r.company,
                            'person_name': r.full_name,
                            'role': r.role,
                            'detail': '',
                            'in_company_results': r.company.nipt in company_nipts,
                        })

    return render(request, 'companies/search.html', {
        'query': query,
        'results': results,
        'result_count': len(results) if isinstance(results, list) else results.count(),
        'person_results': person_results,
        'person_count': len(person_results),
        'on_demand_triggered': on_demand_triggered,
        'limit_reached': limit_reached,
        'searches_remaining': searches_remaining,
        'is_premium': is_premium,
    })


@login_required
def company_detail(request, nipt):
    company = get_object_or_404(Company, nipt=nipt)
    shareholders = company.shareholders.all()
    representatives = company.representatives.all()
    ownership_changes = company.ownership_changes.all()[:20]

    return render(request, 'companies/company_detail.html', {
        'company': company,
        'shareholders': shareholders,
        'representatives': representatives,
        'ownership_changes': ownership_changes,
    })
