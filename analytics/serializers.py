from rest_framework import serializers
from .models import DailyDonationStats, DailyRequestStats, DailyInventorySnapshot


class DailyDonationStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyDonationStats
        fields = '__all__'


class DailyRequestStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyRequestStats
        fields = '__all__'


class DailyInventorySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyInventorySnapshot
        fields = '__all__'


class ReportParametersSerializer(serializers.Serializer):
    """Serializer for validating report generation parameters."""
    report_type = serializers.ChoiceField(choices=[
        'donation_summary', 
        'request_summary',
        'inventory_summary',
        'donation_trends',
        'request_trends',
        'inventory_forecast'
    ])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    format = serializers.ChoiceField(choices=['json', 'pdf', 'excel'], default='json')
    blood_types = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    group_by = serializers.ChoiceField(
        choices=['day', 'week', 'month'],
        default='day'
    )

    def validate(self, data):
        """Validate that start_date is before end_date and date range is reasonable."""
        if data['start_date'] > data['end_date']:
            raise serializers.ValidationError("End date must be after start date")
        
        # Ensure date range is within 365 days
        date_range = (data['end_date'] - data['start_date']).days
        if date_range > 365:
            raise serializers.ValidationError("Date range cannot exceed 365 days")
        
        return data


class ChartDataSerializer(serializers.Serializer):
    """Serializer for chart data responses."""
    labels = serializers.ListField(child=serializers.CharField())
    datasets = serializers.ListField(child=serializers.DictField())
    title = serializers.CharField()
    type = serializers.ChoiceField(choices=['line', 'bar', 'pie', 'doughnut'])


class DashboardMetricsSerializer(serializers.Serializer):
    """Serializer for dashboard overview metrics."""
    donations_today = serializers.IntegerField()
    donations_this_week = serializers.IntegerField()
    donations_this_month = serializers.IntegerField()
    requests_today = serializers.IntegerField()
    requests_this_week = serializers.IntegerField()
    requests_this_month = serializers.IntegerField()
    critical_inventory = serializers.DictField()  # Blood types below critical level
    expiring_soon = serializers.DictField()  # Units expiring in next 7 days