import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, get_user_model
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.db import transaction
from datetime import timedelta

from ..forms import SignUpForm, LoginForm, ResendVerificationForm
from ..models import UserProfile, EmailVerificationLog
from ..utils import get_client_ip, track_click
from .emails import send_verification_email

logger = logging.getLogger('accounts')
User = get_user_model()


def signup_view(request):
    """Handle user registration"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    # Track page view (only for GET requests to avoid double tracking)
    if request.method == 'GET':
        track_click(request, 'signup')
    
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        
        if form.is_valid():
            # Use transaction to ensure atomicity - if email fails, user is still created
            # (Email sending failure shouldn't prevent account creation)
            with transaction.atomic():
                # Create user but don't activate yet
                user = form.save(commit=False)
                user.email = form.cleaned_data.get('email').lower()
                user.is_active = False  # Inactive until email verified
                user.is_email_verified = False
                user.is_premium = False  # New users start as free (non-premium)
                
                # Generate verification token
                token = user.generate_verification_token()
                user.save()
                
                # Create user profile
                UserProfile.objects.create(user=user)
                
                # Log verification attempt
                EmailVerificationLog.objects.create(
                    user=user,
                    token=token,
                    ip_address=get_client_ip(request)
                )
            
            # Send verification email (outside transaction - don't rollback user creation on email failure)
            try:
                send_verification_email(request, user, token)
                messages.success(
                    request,
                    'Account created successfully! Please check your email to verify your account.'
                )
                return redirect('accounts:verification_sent')
            except Exception as e:
                logger.error(f"Failed to send verification email during signup for {user.email}: {e}", exc_info=True)
                messages.error(
                    request,
                    f'Account created successfully! However, we could not send the verification email. '
                    f'Please use the <a href="{reverse("accounts:resend_verification")}">resend verification</a> link.'
                )
                # Redirect to resend verification page
                return redirect('accounts:resend_verification')
        else:
            # Log form errors for debugging
            logger.warning(f"Signup form errors: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SignUpForm()
    
    return render(request, 'accounts/signup.html', {
        'form': form,
    })


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        
        if form.is_valid():
            username_or_email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me', False)
            
            # Try to authenticate with username first
            user = authenticate(username=username_or_email, password=password)
            
            # If failed, try with email as fallback
            if user is None:
                try:
                    user_obj = User.objects.get(email=username_or_email.lower())
                    user = authenticate(username=user_obj.username, password=password)
                except User.DoesNotExist:
                    pass
            
            if user is not None:
                # Superusers can bypass email verification and active checks
                if not user.is_superuser:
                    # Check if email is verified
                    if not user.is_email_verified:
                        messages.error(
                            request,
                            'Please verify your email address before logging in. '
                            '<a href="{}">Resend verification email</a>'.format(
                                reverse('accounts:resend_verification')
                            )
                        )
                        return redirect('accounts:login')
                    
                    # Check if account is active
                    if not user.is_active:
                        messages.error(request, 'Your account has been deactivated.')
                        return redirect('accounts:login')
                
                # Set session expiry
                if not remember_me:
                    request.session.set_expiry(0)  # Session expires on browser close
                else:
                    request.session.set_expiry(1209600)  # 2 weeks
                
                # Log the user in
                login(request, user)
                
                # Update last login
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                logger.info(f"User {user.email} logged in successfully")
                
                # Redirect to next URL or dashboard
                # Validate next_url to prevent open redirect attacks
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure()
                ):
                    return redirect(next_url)
                return redirect('accounts:dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {
        'form': form,
    })


def verify_email(request, token):
    """Handle email verification"""
    try:
        # Find user by token
        user = User.objects.get(
            email_verification_token=token,
            is_email_verified=False
        )
        
        # ALWAYS check expiry - require timestamp to exist
        if not user.email_verification_sent_at:
            logger.warning(f"Verification attempt for {user.email} with missing timestamp")
            messages.error(
                request,
                'Invalid verification link. Please request a new verification email.'
            )
            return redirect('accounts:resend_verification')
        
        # Check if token is expired (24 hours)
        time_diff = timezone.now() - user.email_verification_sent_at
        if time_diff > timedelta(hours=24):
            logger.info(f"Expired verification token attempted for {user.email}")
            messages.error(
                request,
                'Verification link has expired. Please request a new one.'
            )
            return redirect('accounts:resend_verification')
        
        # Verify email and activate account (this clears the token)
        user.verify_email()
        
        # Log verification
        log = EmailVerificationLog.objects.filter(
            user=user,
            token=token
        ).first()
        if log:
            log.verified_at = timezone.now()
            log.ip_address = get_client_ip(request)
            log.save()
        
        # Send welcome email
        from .emails import send_welcome_email
        send_welcome_email(user)
        
        logger.info(f"Email verified for user {user.email}")
        
        # Automatically log the user in after successful verification
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        messages.success(
            request,
            'Email verified successfully! Your account is now active.'
        )
        return redirect('accounts:verification_success')
        
    except User.DoesNotExist:
        logger.warning(f"Invalid verification token attempted: {token}")
        messages.error(request, 'Invalid or expired verification link.')
        return redirect('accounts:login')
    except ValueError as e:
        logger.error(f"Verification error: {e}")
        messages.error(
            request,
            'Invalid verification link. Please request a new verification email.'
        )
        return redirect('accounts:resend_verification')


def resend_verification(request):
    """Resend verification email"""
    if request.method == 'POST':
        form = ResendVerificationForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data.get('email').lower()
            
            try:
                user = User.objects.get(email=email)
                
                if user.is_email_verified:
                    messages.info(request, 'This email is already verified. You can log in.')
                    return redirect('accounts:login')
                
                # Check rate limiting (max 3 emails per hour)
                recent_logs = EmailVerificationLog.objects.filter(
                    user=user,
                    sent_at__gte=timezone.now() - timedelta(hours=1)
                ).count()
                
                if recent_logs >= 3:
                    messages.error(
                        request,
                        'Too many verification emails sent. Please try again in an hour.'
                    )
                    return redirect('accounts:resend_verification')
                
                # Generate new token
                token = user.generate_verification_token()
                user.save()
                
                # Log new verification attempt
                EmailVerificationLog.objects.create(
                    user=user,
                    token=token,
                    ip_address=get_client_ip(request)
                )
                
                # Send verification email
                try:
                    send_verification_email(request, user, token)
                    messages.success(
                        request,
                        'Verification email sent! Please check your inbox.'
                    )
                    return redirect('accounts:verification_sent')
                except Exception as e:
                    logger.error(f"Failed to send verification email during resend for {user.email}: {e}", exc_info=True)
                    messages.error(
                        request,
                        'We could not send the verification email. Please check your email configuration or try again later.'
                    )
                    return redirect('accounts:resend_verification')
                
            except User.DoesNotExist:
                # Don't reveal if email exists or not (security)
                messages.success(
                    request,
                    'If an account exists with this email, a verification link has been sent.'
                )
                return redirect('accounts:verification_sent')
    else:
        form = ResendVerificationForm()
    
    return render(request, 'accounts/resend_verification.html', {
        'form': form,
    })
