from django.urls import path
from .views import (
    DashboardMetricsView,
    GenerateReportView,
    ChartDataView
)

app_name = 'analytics'

urlpatterns = [
    # Dashboard metrics
    path('dashboard/metrics/', DashboardMetricsView.as_view(), name='dashboard_metrics'),
    
    # Report generation
    path('reports/generate/', GenerateReportView.as_view(), name='generate_report'),
    
    # Chart data endpoints
    path('charts/data/', ChartDataView.as_view(), name='chart_data'),
]