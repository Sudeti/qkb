from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import secrets


class User(AbstractUser):
    """Custom User model with email verification"""
    email = models.EmailField(_('email address'), unique=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    welcome_email_sent = models.BooleanField(default=False)
    
    # Optional: Track account status
    is_active = models.BooleanField(default=False)  # Inactive until email verified
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    
    # Premium status (for eu_projects app compatibility)
    is_premium = models.BooleanField(default=False, help_text="Whether user has premium/paying access")

    # Search rate tracking
    searches_today = models.IntegerField(default=0)
    searches_reset_date = models.DateField(null=True, blank=True)
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    
    def __str__(self):
        return self.username
    
    def generate_verification_token(self):
        """Generate a secure verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        return self.email_verification_token
    
    def verify_email(self):
        """Mark email as verified and activate account"""
        self.is_email_verified = True
        self.is_active = True
        self.email_verification_token = None
        self.save(update_fields=['is_email_verified', 'is_active', 'email_verification_token'])
    
    def export_data(self):
        """
        Export all user data in JSON format for GDPR compliance (Right to Data Portability).
        Returns a dictionary with all user-related data.
        """
        data = {
            'user': {
                'username': self.username,
                'email': self.email,
                'first_name': self.first_name,
                'last_name': self.last_name,
                'date_joined': self.date_joined.isoformat() if self.date_joined else None,
                'last_login': self.last_login.isoformat() if self.last_login else None,
                'is_email_verified': self.is_email_verified,
                'is_premium': self.is_premium,
                'is_active': self.is_active,
            },
            'profile': {},
            'verification_logs': [],
        }
        
        # Add profile data if exists
        if hasattr(self, 'profile'):
            profile = self.profile
            data['profile'] = {
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'phone': profile.phone,
                'avatar_url': profile.avatar.url if profile.avatar else None,
                'created_at': profile.created_at.isoformat() if profile.created_at else None,
                'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
            }
        
        # Add verification logs (anonymize IP addresses for privacy)
        if hasattr(self, 'verification_logs'):
            for log in self.verification_logs.all():
                # Anonymize IP: only keep first 2 octets (e.g., 192.168.x.x)
                ip = log.ip_address
                if ip:
                    parts = str(ip).split('.')
                    if len(parts) == 4:
                        ip = f"{parts[0]}.{parts[1]}.x.x"
                
                data['verification_logs'].append({
                    'sent_at': log.sent_at.isoformat() if log.sent_at else None,
                    'verified_at': log.verified_at.isoformat() if log.verified_at else None,
                    'ip_address_anonymized': ip,
                })
        
        return data
    
    def save(self, *args, **kwargs):
        """Override save to ensure superusers are always active and verified"""
        if self.is_superuser:
            self.is_active = True
            self.is_email_verified = True
            # Only set is_premium to True for new superusers (pk is None)
            # This allows admins to toggle it off for existing superusers
            if self.pk is None:
                self.is_premium = True
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    """Basic user profile - extend as needed"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile: {self.user.email}"
    
    @property
    def display_name(self):
        """Get display name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        return self.user.username


class EmailVerificationLog(models.Model):
    """Track email verification attempts"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_logs')
    token = models.CharField(max_length=100)
    sent_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['sent_at']),  # For data retention queries
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.sent_at}"
    
    @classmethod
    def cleanup_old_logs(cls, days=365):
        """
        Delete verification logs older than specified days.
        GDPR compliance: Implement data retention policy.
        """
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_count, _ = cls.objects.filter(sent_at__lt=cutoff_date).delete()
        return deleted_count


class PricingInquiry(models.Model):
    """Stores plan upgrade requests from the pricing page"""
    PLAN_CHOICES = [
        ('professional', 'Professional — EUR 29/month'),
        ('business', 'Business — EUR 79/month'),
    ]

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    company = models.CharField(max_length=300, blank=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Link to user if they're logged in
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pricing_inquiries',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Pricing inquiries'

    def __str__(self):
        return f"{self.full_name} — {self.get_plan_display()} — {self.created_at:%Y-%m-%d}"


class ClickTracking(models.Model):
    """Track page views and clicks for analytics"""
    PAGE_CHOICES = [
        ('signup', 'Sign Up'),
        ('gatekeeper_directory', 'Gatekeeper Directory'),
        ('gatekeeper_detail', 'Gatekeeper Detail'),
        ('institution_rankings', 'Institution Rankings'),
        ('institution_profile', 'Institution Profile'),
        ('project_detail', 'Project Detail'),
        ('regional_rankings', 'Regional Rankings'),
        ('global_institution_rankings', 'Global Institution Rankings'),
        ('gatekeeper_pdf', 'Gatekeeper PDF Download'),
        ('regional_pdf', 'Regional PDF Download'),
    ]
    
    # Page identification
    page_type = models.CharField(max_length=50, choices=PAGE_CHOICES, db_index=True)
    page_url = models.CharField(max_length=500, help_text="Full URL path")
    
    # User information
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='click_tracking',
        help_text="User who clicked (null for anonymous)"
    )
    is_authenticated = models.BooleanField(default=False, db_index=True)
    is_premium = models.BooleanField(default=False, db_index=True)
    
    # Request information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    referer = models.CharField(max_length=500, blank=True)
    
    # Additional context
    country_code = models.CharField(max_length=10, blank=True, help_text="For country-specific pages")
    organization_name = models.CharField(max_length=300, blank=True, help_text="For detail pages")
    region = models.CharField(max_length=10, blank=True, help_text="For regional pages")
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['page_type', '-created_at']),
            models.Index(fields=['is_authenticated', 'is_premium', '-created_at']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = "Click Tracking"
        verbose_name_plural = "Click Tracking"
    
    def __str__(self):
        user_str = self.user.email if self.user else "Anonymous"
        return f"{self.page_type} - {user_str} - {self.created_at}"
    
    @classmethod
    def get_stats(cls, days=30):
        """
        Get aggregated statistics for the last N days.
        Returns dict with various metrics.
        """
        from datetime import timedelta
        from django.db.models import Count, Q
        
        cutoff_date = timezone.now() - timedelta(days=days)
        recent_clicks = cls.objects.filter(created_at__gte=cutoff_date)
        
        total_clicks = recent_clicks.count()
        authenticated_clicks = recent_clicks.filter(is_authenticated=True).count()
        anonymous_clicks = recent_clicks.filter(is_authenticated=False).count()
        premium_clicks = recent_clicks.filter(is_premium=True).count()
        
        # Page type breakdown
        page_stats = recent_clicks.values('page_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Daily breakdown
        daily_stats = recent_clicks.extra(
            select={'day': 'DATE(created_at)'}
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')
        
        # User breakdown (top users)
        user_stats = recent_clicks.filter(user__isnull=False).values(
            'user__email', 'user__is_premium'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:20]
        
        return {
            'total_clicks': total_clicks,
            'authenticated_clicks': authenticated_clicks,
            'anonymous_clicks': anonymous_clicks,
            'premium_clicks': premium_clicks,
            'page_stats': list(page_stats),
            'daily_stats': list(daily_stats),
            'top_users': list(user_stats),
            'period_days': days,
        }