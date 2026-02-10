from django.shortcuts import render, redirect
from django.contrib import messages

from ..forms import PricingInquiryForm


def verification_sent(request):
    """Show verification email sent confirmation"""
    return render(request, 'accounts/verification_sent.html')


def verification_success(request):
    """Show verification success page"""
    return render(request, 'accounts/verification_success.html')


def privacy_policy(request):
    """Display privacy policy and GDPR information"""
    return render(request, 'accounts/privacy_policy.html')


def pricing(request):
    """Display pricing tiers"""
    return render(request, 'accounts/pricing.html')


def request_access(request):
    """Handle plan upgrade request form"""
    if request.method == 'POST':
        form = PricingInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            if request.user.is_authenticated:
                inquiry.user = request.user
            inquiry.save()
            messages.success(request, 'Your request has been submitted. We will contact you within 24 hours.')
            return redirect('accounts:pricing')
    else:
        initial = {}
        plan = request.GET.get('plan')
        if plan in ('professional', 'business'):
            initial['plan'] = plan
        if request.user.is_authenticated:
            initial['email'] = request.user.email
            if hasattr(request.user, 'profile'):
                profile = request.user.profile
                name_parts = [profile.first_name, profile.last_name]
                full = ' '.join(p for p in name_parts if p)
                if full:
                    initial['full_name'] = full
        form = PricingInquiryForm(initial=initial)

    return render(request, 'accounts/request_access.html', {'form': form})
