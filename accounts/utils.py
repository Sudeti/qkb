def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def track_click(request, page_type, **kwargs):
    """
    Track a page view/click for analytics.
    
    Args:
        request: Django request object
        page_type: One of the PAGE_CHOICES from ClickTracking model
        **kwargs: Additional context (country_code, organization_name, region, etc.)
    
    Returns:
        ClickTracking instance (or None if tracking fails, user is superuser, or user is premium)
    
    Note:
        Premium users (paid or provisional) are not tracked for privacy reasons.
    """
    try:
        from .models import ClickTracking
        
        # Skip tracking for superusers and premium users
        if request.user.is_authenticated:
            try:
                request.user.refresh_from_db()
                if request.user.is_superuser:
                    return None  # Don't track superuser clicks
                # Check if user is premium
                if hasattr(request.user, 'is_premium') and request.user.is_premium:
                    return None  # Don't track premium user clicks
            except Exception:
                pass
        
        # Get user info
        user = request.user if request.user.is_authenticated else None
        is_authenticated = request.user.is_authenticated
        is_premium = False
        if is_authenticated:
            try:
                request.user.refresh_from_db()
                is_premium = request.user.is_premium or request.user.is_superuser
            except Exception:
                pass
        
        # Get request info
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        referer = request.META.get('HTTP_REFERER', '')[:500]
        page_url = request.get_full_path()[:500]
        
        # Create tracking record
        tracking = ClickTracking.objects.create(
            page_type=page_type,
            page_url=page_url,
            user=user,
            is_authenticated=is_authenticated,
            is_premium=is_premium,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            country_code=kwargs.get('country_code', ''),
            organization_name=kwargs.get('organization_name', ''),
            region=kwargs.get('region', ''),
        )
        
        return tracking
    except Exception as e:
        # Silently fail tracking to not break the main functionality
        import logging
        logger = logging.getLogger('accounts')
        logger.error(f"Failed to track click: {e}", exc_info=True)
        return None
