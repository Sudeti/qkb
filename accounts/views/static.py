from django.shortcuts import render


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
