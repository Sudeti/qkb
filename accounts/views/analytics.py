import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta

from ..models import ClickTracking

logger = logging.getLogger('accounts')


@login_required
def analytics_dashboard(request):
    """
    Superuser-only analytics dashboard showing click tracking statistics.
    """
    # Only allow superusers
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. This page is only available to administrators.')
        return redirect('accounts:dashboard')
    
    # Get time period from request (default to 30 days)
    days = int(request.GET.get('days', 30))
    if days < 1 or days > 365:
        days = 30
    
    # Get stats
    stats = ClickTracking.get_stats(days=days)
    
    # Add display names to page stats
    page_type_display_names = {
        'signup': 'Sign Up',
        'gatekeeper_directory': 'Gatekeeper Directory',
        'gatekeeper_detail': 'Gatekeeper Detail',
        'institution_rankings': 'Institution Rankings',
        'institution_profile': 'Institution Profile',
        'project_detail': 'Project Detail',
        'regional_rankings': 'Regional Rankings',
        'global_institution_rankings': 'Global Institution Rankings',
        'gatekeeper_pdf': 'Gatekeeper PDF Download',
        'regional_pdf': 'Regional PDF Download',
    }
    
    # Add display names to page_stats
    for page_stat in stats['page_stats']:
        page_stat['display_name'] = page_type_display_names.get(
            page_stat['page_type'], 
            page_stat['page_type'].replace('_', ' ').title()
        )
    
    # Additional detailed stats
    cutoff_date = timezone.now() - timedelta(days=days)
    recent_clicks = ClickTracking.objects.filter(created_at__gte=cutoff_date)
    
    # Hourly breakdown for last 24 hours
    last_24h = timezone.now() - timedelta(hours=24)
    hourly_stats = recent_clicks.filter(created_at__gte=last_24h).extra(
        select={'hour': "EXTRACT(HOUR FROM created_at)"}
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')
    
    # Top referrers
    top_referrers = recent_clicks.exclude(referer='').values('referer').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # User type breakdown (premium users are not tracked, so only anonymous and authenticated free users)
    user_type_stats = {
        'anonymous': recent_clicks.filter(is_authenticated=False).count(),
        'authenticated_free': recent_clicks.filter(is_authenticated=True, is_premium=False).count(),
        'authenticated_premium': recent_clicks.filter(is_premium=True).count(),
    }
    
    # Country breakdown (for country-specific pages)
    country_stats = recent_clicks.exclude(country_code='').values('country_code').annotate(
        count=Count('id')
    ).order_by('-count')[:20]
    
    # Region breakdown
    region_stats = recent_clicks.exclude(region='').values('region').annotate(
        count=Count('id')
    ).order_by('-count')
    
    context = {
        'stats': stats,
        'hourly_stats': list(hourly_stats),
        'top_referrers': list(top_referrers),
        'user_type_stats': user_type_stats,
        'country_stats': list(country_stats),
        'region_stats': list(region_stats),
        'days': days,
        'total_tracking_records': ClickTracking.objects.count(),
    }
    
    return render(request, 'accounts/analytics_dashboard.html', context)
