from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('search/', views.search, name='search'),
    path('company/<str:nipt>/', views.company_detail, name='company_detail'),
]
