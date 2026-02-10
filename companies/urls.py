from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path('', views.search, name='search'),
    path('company/<str:nipt>/', views.company_detail, name='company_detail'),
]
