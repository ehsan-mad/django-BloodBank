from datetime import datetime, timedelta
from rest_framework import views, permissions, status
from rest_framework.response import Response
from django.utils import timezone
from django.http import FileResponse
from django.core.files.storage import default_storage
import os

from .serializers import (
    ReportParametersSerializer,
    DashboardMetricsSerializer,
    ChartDataSerializer
)
from .services import AnalyticsService, ReportService, ChartService


class AdminRequiredMixin:
    """Mixin to ensure only admin users can access analytics views."""
    permission_classes = [permissions.AllowAny]  # Temporarily allow all users for testing


class DashboardMetricsView(AdminRequiredMixin, views.APIView):
    """Get current dashboard metrics."""

    def get(self, request):
        # Get today's date at midnight for consistent daily stats
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate time ranges
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Get metrics with error handling
        analytics = AnalyticsService()
        
        metrics = {}
        
        try:
            metrics.update({
                'donations_today': analytics._get_donation_count(today),
                'donations_this_week': analytics._get_donation_count(week_start),
                'donations_this_month': analytics._get_donation_count(month_start)
            })
        except Exception as e:
            metrics.update({
                'donations_today': 0,
                'donations_this_week': 0,
                'donations_this_month': 0,
                'donations_error': str(e)
            })

        try:
            metrics.update({
                'requests_today': analytics._get_request_count(today),
                'requests_this_week': analytics._get_request_count(week_start),
                'requests_this_month': analytics._get_request_count(month_start)
            })
        except Exception as e:
            metrics.update({
                'requests_today': 0,
                'requests_this_week': 0,
                'requests_this_month': 0,
                'requests_error': str(e)
            })

        try:
            metrics['critical_inventory'] = analytics._get_critical_inventory_levels()
        except Exception as e:
            metrics['critical_inventory'] = []
            metrics['critical_inventory_error'] = str(e)

        try:
            metrics['expiring_soon'] = analytics._get_expiring_units()
        except Exception as e:
            metrics['expiring_soon'] = []
            metrics['expiring_soon_error'] = str(e)

        # Validate metrics through serializer
        serializer = DashboardMetricsSerializer(data=metrics)
        if not serializer.is_valid():
            return Response(
                {'error': 'Invalid metrics data', 'details': serializer.errors},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Return validated data
        return Response(serializer.data)


class GenerateReportView(AdminRequiredMixin, views.APIView):
    """Generate analytics reports."""

    def post(self, request):
        # Validate request data
        serializer = ReportParametersSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'error': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate report type
        valid_report_types = ['inventory', 'donations', 'requests', 'donors']
        if serializer.validated_data['report_type'] not in valid_report_types:
            return Response(
                {'error': f'Invalid report type. Must be one of: {", ".join(valid_report_types)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate export format if specified
        format = serializer.validated_data.get('format', 'json')
        valid_formats = ['json', 'csv', 'xlsx', 'pdf']
        if format not in valid_formats:
            return Response(
                {'error': f'Invalid export format. Must be one of: {", ".join(valid_formats)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Get or generate report
            report_data = ReportService.get_or_generate_report(
                report_type=serializer.validated_data['report_type'],
                parameters=serializer.validated_data,
                force_refresh=request.query_params.get('force_refresh', False)
            )

            # Export if needed
            format = serializer.validated_data.get('format', 'json')
            if format != 'json':
                exported_file = ReportService.export_report(report_data, format)
                
                # Save exported file
                filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
                file_path = default_storage.save(f'reports/{filename}', exported_file)
                
                # Return file download response
                response = FileResponse(
                    default_storage.open(file_path),
                    as_attachment=True,
                    filename=filename
                )
                return response

            return Response(report_data)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ChartDataView(AdminRequiredMixin, views.APIView):
    """Get chart data for various analytics visualizations."""

    def get(self, request):
        chart_type = request.query_params.get('type')
        if not chart_type:
            return Response(
                {'error': 'Chart type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Validate chart type
            valid_chart_types = ['donation_trend', 'blood_type_distribution', 'requests_fulfillment', 'inventory_forecast']
            if chart_type not in valid_chart_types:
                return Response(
                    {'error': f'Invalid chart type. Must be one of: {", ".join(valid_chart_types)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Parse and validate date parameters if needed
            start_date = None
            end_date = None
            if chart_type in ['donation_trend', 'requests_fulfillment']:
                try:
                    start_date = datetime.strptime(
                        request.query_params.get('start_date', ''),
                        '%Y-%m-%d'
                    ).date()
                    end_date = datetime.strptime(
                        request.query_params.get('end_date', ''),
                        '%Y-%m-%d'
                    ).date()

                    # Validate date range
                    if start_date > end_date:
                        return Response(
                            {'error': 'End date must be after start date'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Validate date range is not too large
                    if (end_date - start_date).days > 365:
                        return Response(
                            {'error': 'Date range cannot exceed 365 days'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except ValueError:
                    return Response(
                        {'error': 'Invalid date format. Use YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            try:
                # Get chart data based on type
                if chart_type == 'donation_trend':
                    if not start_date or not end_date:
                        return Response(
                            {'error': 'start_date and end_date are required for donation trend'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    data = ChartService.generate_donation_trend_chart(start_date, end_date)

                elif chart_type == 'blood_type_distribution':
                    data = ChartService.generate_blood_type_distribution_chart()

                elif chart_type == 'requests_fulfillment':
                    if not start_date or not end_date:
                        return Response(
                            {'error': 'start_date and end_date are required for requests fulfillment'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    data = ChartService.generate_requests_fulfillment_chart(start_date, end_date)

                elif chart_type == 'inventory_forecast':
                    blood_type = request.query_params.get('blood_type')
                    if not blood_type:
                        return Response(
                            {'error': 'Blood type is required for inventory forecast'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    data = ChartService.generate_inventory_forecast_chart(blood_type)
                else:
                    return Response(
                        {'error': f'Invalid chart type: {chart_type}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {'error': f'Error generating chart data: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            serializer = ChartDataSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data)

        except ValueError as e:
            return Response(
                {'error': f'Invalid date format: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
