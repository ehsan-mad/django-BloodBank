from django.urls import path
from . import views

urlpatterns = [
    # Inventory
    path('inventory/', views.InventoryListView.as_view(), name='inventory-list'),
    
    # Donations
    path('donations/', views.DonationListView.as_view(), name='donation-list'),
    path('donations/create/', views.DonationCreateView.as_view(), name='donation-create'),
    path('donations/<int:pk>/', views.DonationDetailView.as_view(), name='donation-detail'),
    path('donations/<int:pk>/action/', views.DonationActionView.as_view(), name='donation-action'),
    
    # Blood Requests
    path('requests/', views.BloodRequestListView.as_view(), name='request-list'),
    path('requests/create/', views.BloodRequestCreateView.as_view(), name='request-create'),
    path('requests/<int:pk>/', views.BloodRequestDetailView.as_view(), name='request-detail'),
    path('requests/<int:pk>/action/', views.BloodRequestActionView.as_view(), name='request-action'),
    
    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
]