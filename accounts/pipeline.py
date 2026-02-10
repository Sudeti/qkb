import logging
from social_core.exceptions import AuthException
from django.contrib.auth import get_user_model
from .models import UserProfile
from .views import send_welcome_email

logger = logging.getLogger('accounts')
User = get_user_model()


def check_existing_user_by_email(backend, details, response, social=None, *args, **kwargs):
    """
    Check if a user with this email already exists.
    If yes, associate the social account with the existing user instead of creating a new one.
    This prevents IntegrityError when trying to create a user with an existing email.
    
    This function runs AFTER social_user step, so if social_user found a user, we don't need to check.
    We only check if social_user didn't find a user (user is None) but email exists in our system.
    """
    # If social_user step already found a user, don't do anything
    if social and social.user:
        logger.info(f"Social account already associated with user {social.user.username}")
        return None
    
    email = details.get('email', '').lower().strip()
    if not email:
        return None
    
    try:
        existing_user = User.objects.get(email=email)
        logger.info(f"Found existing user with email {email}: {existing_user.username}")
        
        # Check if this social account (Google ID) is already associated with a different user
        from social_django.models import UserSocialAuth
        
        # Get the UID from various possible sources
        uid = None
        if social and hasattr(social, 'uid'):
            uid = social.uid
        elif 'uid' in kwargs:
            uid = kwargs['uid']
        elif response and 'id' in response:
            uid = str(response['id'])
        
        if uid:
            social_auth = UserSocialAuth.objects.filter(
                provider=backend.name,
                uid=uid
            ).first()
            
            if social_auth and social_auth.user != existing_user:
                # Social account is associated with a different user
                logger.warning(
                    f"Social account {backend.name} (uid={uid}) is already associated with user {social_auth.user.username}, "
                    f"but email {email} belongs to user {existing_user.username}"
                )
                raise AuthException(
                    backend,
                    "This Google account is already linked to a different account. "
                    "Please log in with your existing account or contact support."
                )
        
        # Return the existing user - this will skip the create_user step
        # The associate_user step will link the social account to this user
        logger.info(f"Will associate social account with existing user {existing_user.username}")
        
        # Store a message to show the user that their Google account was linked
        # This will be picked up in a later pipeline step or view
        return {
            'user': existing_user,
            'is_new': False,
            'social_account_linked': True,  # Flag to show message later
        }
    except User.DoesNotExist:
        # User doesn't exist, let the normal create_user step handle it
        logger.info(f"No existing user found with email {email}, will create new user")
        return None
    except User.MultipleObjectsReturned:
        # This shouldn't happen due to unique constraint, but handle it just in case
        logger.error(f"Multiple users found with email {email}")
        existing_user = User.objects.filter(email=email).first()
        return {
            'user': existing_user,
            'is_new': False,
        }


def create_user_profile(backend, user, response, *args, **kwargs):
    """Create user profile for social authentication pipeline"""
    logger.info(f"Processing social auth pipeline for user: {user.username}")
    logger.info(f"Backend: {backend.name}")
    
    # Check if this is linking to an existing account
    social_account_linked = kwargs.get('social_account_linked', False)
    
    # Create profile if it doesn't exist
    profile, created = UserProfile.objects.get_or_create(user=user, defaults={'institution': ''})
    if created:
        logger.info(f"Created new profile for user: {user.username}")
        
        # Try to populate profile from social data
        if backend.name == 'google-oauth2':
            profile.first_name = response.get('given_name', '')
            profile.last_name = response.get('family_name', '')
            profile.save()
    
    # Mark email as verified and activate account for social auth
    if not user.is_email_verified:
        logger.info(f"Setting email as verified for social auth user: {user.username}")
        user.is_email_verified = True
        user.is_active = True
        user.save(update_fields=['is_email_verified', 'is_active'])
    
    result = {'user': user, 'profile': profile}
    if social_account_linked:
        result['social_account_linked'] = True
    
    return result


def send_welcome_email_social(backend, user, response, *args, **kwargs):
    """Send welcome email to new users who sign up via social auth"""
    is_new = kwargs.get('is_new', False)
    
    if is_new and not user.welcome_email_sent:
        logger.info(f"Sending welcome email via social auth pipeline for {user.email}")
        send_welcome_email(user)
