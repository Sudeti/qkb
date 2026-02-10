from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Email verification
    path('verify/<str:token>/', views.verify_email, name='verify_email'),
    path('verification-sent/', views.verification_sent, name='verification_sent'),
    path('verification-success/', views.verification_success, name='verification_success'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),
    
    # Dashboard and profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/update/', views.profile_update, name='profile_update'),
    
    # GDPR compliance
    path('export-data/', views.export_data, name='export_data'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('pricing/', views.pricing, name='pricing'),
    path('request-access/', views.request_access, name='request_access'),
    
    # Analytics (superuser only)
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
]
