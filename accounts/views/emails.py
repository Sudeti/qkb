import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site

logger = logging.getLogger('accounts')


def send_verification_email(request, user, token):
    """Send verification email to user"""
    try:
        current_site = get_current_site(request)
        verification_url = request.build_absolute_uri(
            reverse('accounts:verify_email', args=[token])
        )
        
        subject = 'Verify your email address'
        
        html_message = render_to_string('accounts/emails/email_verification.html', {
            'user': user,
            'verification_url': verification_url,
            'domain': current_site.domain,
            'site_name': 'QKB Intelligence',
        })
        
        text_message = f"""
        Welcome to QKB Intelligence!
        
        Please verify your email address by clicking the link below:
        {verification_url}
        
        This link will expire in 24 hours.
        
        If you didn't create an account, please ignore this email.
        """
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@QKB Intelligence'),
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        
        # Log email configuration for debugging
        logger.info(f"Attempting to send verification email to {user.email} from {getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@QKB Intelligence')}")
        logger.info(f"Email backend: {settings.EMAIL_BACKEND}")
        
        # Send email
        email.send(fail_silently=False)
        
        # Check Anymail status if available
        if hasattr(email, 'anymail_status'):
            logger.info(f"Anymail status: {email.anymail_status}")
        if hasattr(email, 'anymail_status') and email.anymail_status.status:
            for recipient, status in email.anymail_status.recipients.items():
                logger.info(f"Email status for {recipient}: {status}")
        
        logger.info(f"Verification email sent to {user.email}")
        
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {e}", exc_info=True)
        # Re-raise the exception so the caller knows email sending failed
        raise


def send_welcome_email(user):
    """Send welcome email after verification"""
    # Prevent duplicate emails
    if user.welcome_email_sent:
        return
    
    try:
        from django.contrib.sites.models import Site
        
        current_site = Site.objects.get_current()
        site_url = getattr(settings, 'SITE_URL', f'http://{current_site.domain}')
        login_url = f"{site_url}{reverse('accounts:login')}"
        
        subject = 'Welcome to QKB Intelligence!'
        
        html_message = render_to_string('accounts/emails/welcome_email.html', {
            'user': user,
            'login_url': login_url,
            'site_name': 'QKB Intelligence',
            'site_url': site_url,
        })
        
        text_message = f"""
        Welcome to QKB Intelligence!
        
        Your account has been successfully activated.
        
        You can now log in at: {login_url}
        
        Thank you for joining us!
        """
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@QKB Intelligence'),
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=True)
        
        # Mark welcome email as sent
        user.welcome_email_sent = True
        user.save(update_fields=['welcome_email_sent'])
        
        logger.info(f"Welcome email sent to {user.email}")
        
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}")
