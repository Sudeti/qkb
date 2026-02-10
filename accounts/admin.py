from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib import messages
from django.utils import timezone
import logging
from .models import (
    User, UserProfile, EmailVerificationLog, ClickTracking
)

logger = logging.getLogger('accounts')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model"""
    list_display = ('email', 'username', 'is_email_verified', 'is_active', 'is_premium', 'date_joined', 'last_login')
    list_filter = ('is_email_verified', 'is_active', 'is_premium', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'username')
    ordering = ('-date_joined',)
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Email Verification', {
            'fields': ('is_email_verified', 'email_verification_token', 'email_verification_sent_at', 'welcome_email_sent')
        }),
        ('Premium Status', {
            'fields': ('is_premium',)
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Email Verification', {
            'fields': ('email',)
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile model"""
    list_display = ('user', 'display_name', 'phone', 'created_at')
    search_fields = ('user__email', 'user__username', 'first_name', 'last_name')
    list_filter = ('created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(EmailVerificationLog)
class EmailVerificationLogAdmin(admin.ModelAdmin):
    """Admin for EmailVerificationLog model"""
    list_display = ('user', 'sent_at', 'verified_at', 'ip_address')
    list_filter = ('sent_at', 'verified_at')
    search_fields = ('user__email', 'user__username', 'ip_address')
    readonly_fields = ('user', 'token', 'sent_at', 'verified_at', 'ip_address')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ClickTracking)
class ClickTrackingAdmin(admin.ModelAdmin):
    """Admin for ClickTracking model"""
    list_display = ('page_type', 'user', 'is_authenticated', 'is_premium', 'ip_address', 'created_at')
    list_filter = ('page_type', 'is_authenticated', 'is_premium', 'created_at')
    search_fields = ('page_type', 'page_url', 'user__email', 'user__username', 'ip_address', 'organization_name', 'country_code')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Page Information', {
            'fields': ('page_type', 'page_url', 'created_at')
        }),
        ('User Information', {
            'fields': ('user', 'is_authenticated', 'is_premium')
        }),
        ('Request Information', {
            'fields': ('ip_address', 'user_agent', 'referer')
        }),
        ('Context', {
            'fields': ('country_code', 'organization_name', 'region')
        }),
    )
    
    def has_add_permission(self, request):
        return False  # Only created through tracking, not manually