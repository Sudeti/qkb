import re
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q
from .models import Company


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


@login_required
def search(request):
    query = request.GET.get('q', '').strip()
    results = []
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
                    # Fallback to icontains for companies without populated search_vector
                    results = Company.objects.filter(
                        Q(name__icontains=query) |
                        Q(name_latin__icontains=query) |
                        Q(shareholders__full_name__icontains=query) |
                        Q(representatives__full_name__icontains=query)
                    ).distinct()[:50]

                # If query looks like a NIPT and no results, trigger on-demand scrape
                if not results and NIPT_PATTERN.match(query):
                    from .tasks import scrape_single_nipt_task
                    scrape_single_nipt_task.delay(query.upper())
                    on_demand_triggered = True

    return render(request, 'companies/search.html', {
        'query': query,
        'results': results,
        'result_count': len(results) if isinstance(results, list) else results.count(),
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
