from django.urls import path
from . import views

app_name = 'monitor'

urlpatterns = [
    path('', views.home, name='home'),
    path('price-chart/', views.price_chart, name='price_chart'),
    path('price-overview/', views.price_overview, name='price_overview'),
    path('crawler/', views.crawler, name='crawler'),
    path('strategy/', views.trading_strategy, name='trading_strategy')
]  