"""
Views module for accounts app.

This module imports all views from submodules to maintain backward compatibility
with existing URL patterns that use `from . import views`.
"""

# Authentication views
from .auth import (
    signup_view,
    login_view,
    verify_email,
    resend_verification,
)

# User management views
from .user import (
    dashboard,
    profile_update,
    logout_view,
    export_data,
    delete_account,
)

# Static pages
from .static import (
    verification_sent,
    verification_success,
    privacy_policy,
    pricing,
)

# Analytics views
from .analytics import (
    analytics_dashboard,
)

# Email functions (not typically used as views, but available if needed)
from .emails import (
    send_verification_email,
    send_welcome_email,
)

__all__ = [
    # Authentication
    'signup_view',
    'login_view',
    'verify_email',
    'resend_verification',
    # User management
    'dashboard',
    'profile_update',
    'logout_view',
    'export_data',
    'delete_account',
    # Static pages
    'verification_sent',
    'verification_success',
    'privacy_policy',
    'pricing',
    # Analytics
    'analytics_dashboard',
    # Email functions
    'send_verification_email',
    'send_welcome_email',
]
