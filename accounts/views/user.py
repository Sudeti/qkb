import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import ProfileUpdateForm
from ..models import UserProfile

logger = logging.getLogger('accounts')


@login_required
def dashboard(request):
    """User dashboard"""
    from datetime import date

    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Check if profile is incomplete (missing institution or position)
    # Redirect to profile update if incomplete
    if not profile.institution or not profile.position:
        messages.info(
            request,
            'Please complete your profile by providing your institution and position.'
        )
        return redirect('accounts:profile_update')

    # Search usage stats
    is_premium = user.is_premium or user.is_superuser
    daily_limit = 0 if is_premium else 10
    today = date.today()
    searches_today = user.searches_today if user.searches_reset_date == today else 0
    searches_remaining = max(0, daily_limit - searches_today) if not is_premium else None
    search_usage_pct = int((searches_today / daily_limit) * 100) if daily_limit > 0 else 0

    context = {
        'user': user,
        'profile': profile,
        'is_premium': is_premium,
        'daily_limit': daily_limit,
        'searches_today': searches_today,
        'searches_remaining': searches_remaining,
        'search_usage_pct': min(search_usage_pct, 100),
    }

    return render(request, 'accounts/dashboard.html', context)


@login_required
def profile_update(request):
    """Update user profile"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:dashboard')
    else:
        form = ProfileUpdateForm(instance=profile)
    
    return render(request, 'accounts/profile_update.html', {
        'form': form,
    })


@login_required
def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')


@login_required
def export_data(request):
    """Export user data in JSON format (GDPR Right to Data Portability)"""
    user = request.user
    data = user.export_data()
    
    response = JsonResponse(data, json_dumps_params={'indent': 2})
    filename = f"user_data_{user.username}_{timezone.now().strftime('%Y%m%d')}.json"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Type'] = 'application/json'
    
    logger.info(f"User {user.email} exported their data")
    return response


@login_required
@require_POST
def delete_account(request):
    """Delete user account and all associated data (GDPR Right to Erasure)"""
    user = request.user
    
    # Prevent superusers from deleting themselves via web interface
    if user.is_superuser:
        messages.error(request, 'Superuser accounts cannot be deleted through this interface.')
        return redirect('accounts:dashboard')
    
    # Log the deletion
    logger.info(f"User {user.email} requested account deletion")
    
    # Delete user (CASCADE will handle related objects)
    email = user.email
    user.delete()
    
    # Logout user
    logout(request)
    
    messages.success(
        request,
        'Your account and all associated data have been permanently deleted. '
        'We are sorry to see you go!'
    )
    return redirect('accounts:login')
