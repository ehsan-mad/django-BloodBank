from datetime import timedelta, datetime
import json
import pandas as pd
import numpy as np
from django.utils import timezone
from django.db import models
from django.db.models import Count, Q, Sum, Avg
from django.core.cache import cache
from django.conf import settings
from donations.models import Donation, BloodRequest, Inventory, InventoryTransaction
from accounts.models import BLOOD_GROUP_CHOICES
from .models import DailyDonationStats, DailyRequestStats, DailyInventorySnapshot, ReportCache
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet


class AnalyticsService:
    @classmethod
    def generate_daily_stats(cls, date=None):
        """Generate analytics for a specific date"""
        if date is None:
            date = timezone.now().date()

        # Generate donation statistics
        cls._generate_donation_stats(date)
        
        # Generate request statistics
        cls._generate_request_stats(date)
        
        # Generate inventory snapshot
        cls._generate_inventory_snapshot(date)

    @classmethod
    def _get_donation_count(cls, start_date):
        """Get donation count from a specific date."""
        return Donation.objects.filter(
            request_date__gte=start_date
        ).count()

    @classmethod
    def _get_request_count(cls, start_date):
        """Get request count from a specific date."""
        return BloodRequest.objects.filter(
            request_date__gte=start_date
        ).count()

    @classmethod
    def _get_critical_inventory_levels(cls):
        """Get blood types with critically low inventory."""
        critical_levels = {}
        for inv in Inventory.objects.filter(is_low=True):
            critical_levels[inv.blood_group] = inv.quantity
        return critical_levels

    @classmethod
    def _get_expiring_units(cls):
        """Get blood units that will need replenishment soon."""
        # Since we don't track individual units with expiry dates,
        # we'll estimate based on low stock and recent activity
        expiring = {}
        for inv in Inventory.objects.filter(is_low=True):
            # Consider low stock items as needing replenishment
            expiring[inv.blood_group] = inv.quantity
        return expiring

    @classmethod
    def _generate_donation_stats(cls, date):
        """Generate donation statistics for a specific date"""
        donations = Donation.objects.filter(request_date__date=date)
        
        # Calculate overall stats
        total = donations.count()
        successful = donations.filter(status='approved').count()
        rejected = donations.filter(status='rejected').count()
        
        # Calculate blood group breakdown
        breakdown = {}
        for blood_group, _ in BLOOD_GROUP_CHOICES:
            group_donations = donations.filter(blood_group=blood_group)
            breakdown[blood_group] = {
                'total': group_donations.count(),
                'successful': group_donations.filter(status='approved').count(),
                'rejected': group_donations.filter(status='rejected').count(),
            }
        
        # Create or update daily stats
        DailyDonationStats.objects.update_or_create(
            date=date,
            defaults={
                'total_donations': total,
                'successful_donations': successful,
                'rejected_donations': rejected,
                'blood_type_breakdown': breakdown
            }
        )

    @classmethod
    def _generate_request_stats(cls, date):
        """Generate request statistics for a specific date"""
        requests = BloodRequest.objects.filter(request_date__date=date)
        
        # Calculate overall stats
        total = requests.count()
        fulfilled = requests.filter(status='fulfilled').count()
        pending = requests.filter(status='pending').count()
        cancelled = requests.filter(status='cancelled').count()
        
        # Calculate blood group breakdown
        breakdown = {}
        urgency_breakdown = {'urgent': 0, 'normal': 0}
        
        for blood_group, _ in BLOOD_GROUP_CHOICES:
            group_requests = requests.filter(blood_group=blood_group)
            breakdown[blood_group] = {
                'total': group_requests.count(),
                'fulfilled': group_requests.filter(status='fulfilled').count(),
                'pending': group_requests.filter(status='pending').count(),
                'cancelled': group_requests.filter(status='cancelled').count()
            }
        
        # Calculate urgency breakdown
        urgency_breakdown['urgent'] = requests.filter(urgency=True).count()
        urgency_breakdown['normal'] = requests.filter(urgency=False).count()
        
        # Create or update daily stats
        DailyRequestStats.objects.update_or_create(
            date=date,
            defaults={
                'total_requests': total,
                'fulfilled_requests': fulfilled,
                'pending_requests': pending,
                'cancelled_requests': cancelled,
                'blood_type_breakdown': breakdown,
                'urgency_breakdown': urgency_breakdown
            }
        )

    @classmethod
    def _generate_inventory_snapshot(cls, date):
        """Generate inventory snapshot for a specific date"""
        inventory = Inventory.objects.all()
        
        # Calculate inventory levels and expiring units
        levels = {}
        expiring_soon = {}
        expired_today = {}
        today = timezone.now().date()
        week_later = today + timedelta(days=7)
        
        for inv in inventory:
            # Current inventory levels
            levels[inv.blood_group] = inv.quantity
            
            # Since we don't track expiry dates directly, we'll use is_low flag
            if inv.is_low:
                expiring_soon[inv.blood_group] = inv.quantity
                
            # For expired units, we'll check recent transactions
            recent_transactions = InventoryTransaction.objects.filter(
                inventory=inv,
                timestamp__date=today
            ).aggregate(
                models.Sum('quantity')
            )['quantity__sum'] or 0
            
            if recent_transactions < 0:  # Negative transactions indicate usage/expiry
                expired_today[inv.blood_group] = abs(recent_transactions)
        
        # Create or update snapshot
        DailyInventorySnapshot.objects.update_or_create(
            date=date,
            defaults={
                'inventory_levels': levels,
                'expiring_soon': expiring_soon,
                'expired_today': expired_today
            }
        )


class ReportService:
    CACHE_PREFIX = 'report_cache_'
    CACHE_DURATION = timedelta(hours=24)  # Cache reports for 24 hours

    @classmethod
    def get_or_generate_report(cls, report_type, parameters, force_refresh=False):
        """Get a cached report or generate a new one."""
        # Convert dates to strings in parameters to ensure JSON serialization
        processed_params = parameters.copy()
        if 'start_date' in processed_params:
            processed_params['start_date'] = processed_params['start_date'].isoformat()
        if 'end_date' in processed_params:
            processed_params['end_date'] = processed_params['end_date'].isoformat()
        
        cache_key = cls._get_cache_key(report_type, processed_params)
        
        if not force_refresh:
            cached_report = ReportCache.objects.filter(
                report_type=report_type,
                parameters=processed_params,
                expires_at__gt=timezone.now(),
                is_generating=False
            ).first()
            
            if cached_report:
                return cached_report.data

        # Lock report generation
        lock = cls._acquire_generation_lock(cache_key)
        if not lock:
            raise ValueError("Report generation already in progress")

        try:
            data = cls._generate_report(report_type, parameters)
            cls._cache_report(report_type, parameters, data)
            return data
        finally:
            cls._release_generation_lock(cache_key)

    @classmethod
    def _generate_report(cls, report_type, parameters):
        """Generate a report based on type and parameters."""
        generators = {
            'donation_summary': cls._generate_donation_summary,
            'request_summary': cls._generate_request_summary,
            'inventory_summary': cls._generate_inventory_summary,
            'donation_trends': cls._generate_donation_trends,
            'request_trends': cls._generate_request_trends,
            'inventory_forecast': cls._generate_inventory_forecast
        }

        if report_type not in generators:
            raise ValueError(f"Invalid report type: {report_type}")

        return generators[report_type](parameters)

    @classmethod
    def _generate_request_trends(cls, parameters):
        """Generate detailed blood request trends analysis."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')
        group_by = parameters.get('group_by', 'day')

        # Get base queryset
        requests = DailyRequestStats.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(list(requests.values()))
        
        if df.empty:
            return {
                'trends': {
                    'labels': [],
                    'datasets': []
                },
                'analysis': {
                    'request_trend': 'insufficient_data',
                    'fulfillment_trend': 'insufficient_data',
                    'peak_day': None,
                    'most_urgent_day': None,
                    'blood_type_insights': {},
                    'urgency_analysis': {
                        'urgent': 0,
                        'normal': 0,
                        'urgent_fulfillment_rate': 0
                    }
                }
            }

        # Group by time period if needed
        if group_by == 'week':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('W', on='date').sum()
        elif group_by == 'month':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('M', on='date').sum()

        # Calculate fulfillment rates
        df['fulfillment_rate'] = (df['fulfilled_requests'] / df['total_requests'] * 100).fillna(0)

        # Calculate trends using simple linear regression
        x = np.arange(len(df))
        
        # Total requests trend
        total_slope, _ = np.polyfit(x, df['total_requests'], 1)
        request_trend = 'increasing' if total_slope > 0.1 else 'decreasing' if total_slope < -0.1 else 'stable'

        # Fulfillment rate trend
        fulfillment_slope, _ = np.polyfit(x, df['fulfillment_rate'], 1)
        fulfillment_trend = 'improving' if fulfillment_slope > 0.1 else 'declining' if fulfillment_slope < -0.1 else 'stable'

        # Find peak and most urgent days
        peak_idx = df['total_requests'].idxmax()
        
        # Blood type analysis
        blood_type_insights = {}
        urgency_stats = {'urgent': 0, 'normal': 0}
        urgent_fulfilled = 0

        for request in requests:
            # Process blood type breakdown
            breakdown = request.blood_type_breakdown
            if isinstance(breakdown, str):
                try:
                    breakdown = json.loads(breakdown)
                except json.JSONDecodeError:
                    continue

            for blood_type, data in breakdown.items():
                if blood_types and blood_type not in blood_types:
                    continue
                if blood_type not in blood_type_insights:
                    blood_type_insights[blood_type] = {
                        'total': 0,
                        'fulfilled': 0,
                        'pending': 0,
                        'cancelled': 0,
                        'fulfillment_rate': 0
                    }
                blood_type_insights[blood_type]['total'] += int(data.get('total', 0))
                blood_type_insights[blood_type]['fulfilled'] += int(data.get('fulfilled', 0))
                blood_type_insights[blood_type]['pending'] += int(data.get('pending', 0))
                blood_type_insights[blood_type]['cancelled'] += int(data.get('cancelled', 0))

            # Process urgency breakdown
            urgency = request.urgency_breakdown
            if isinstance(urgency, str):
                try:
                    urgency = json.loads(urgency)
                except json.JSONDecodeError:
                    continue
                    
            urgency_stats['urgent'] += int(urgency.get('urgent', 0))
            urgency_stats['normal'] += int(urgency.get('normal', 0))

            # Track fulfilled urgent requests
            if isinstance(request.blood_type_breakdown, str):
                try:
                    type_data = json.loads(request.blood_type_breakdown)
                    for blood_data in type_data.values():
                        urgent_fulfilled += int(blood_data.get('fulfilled', 0))
                except json.JSONDecodeError:
                    continue

        # Calculate fulfillment rates for blood types
        for blood_type in blood_type_insights:
            total = blood_type_insights[blood_type]['total']
            if total > 0:
                fulfillment_rate = (blood_type_insights[blood_type]['fulfilled'] / total) * 100
                blood_type_insights[blood_type]['fulfillment_rate'] = round(float(fulfillment_rate), 2)

        # Calculate urgent request fulfillment rate
        total_urgent = urgency_stats['urgent']
        urgent_fulfillment_rate = (urgent_fulfilled / total_urgent * 100) if total_urgent > 0 else 0

        # Find day with most urgent requests
        urgent_by_day = {}
        for request in requests:
            date_str = request.date.strftime('%Y-%m-%d')
            urgency = request.urgency_breakdown
            if isinstance(urgency, str):
                try:
                    urgency = json.loads(urgency)
                except json.JSONDecodeError:
                    continue
            urgent_by_day[date_str] = urgent_by_day.get(date_str, 0) + int(urgency.get('urgent', 0))
        
        most_urgent_day = max(urgent_by_day.items(), key=lambda x: x[1])[0] if urgent_by_day else None

        # Prepare trend data
        trends_data = {
            'labels': df.index.strftime('%Y-%m-%d').tolist() if hasattr(df.index, 'strftime') else [d.strftime('%Y-%m-%d') for d in df.index],
            'datasets': [
                {
                    'label': 'Total Requests',
                    'data': [int(x) for x in df['total_requests'].tolist()]
                },
                {
                    'label': 'Fulfilled Requests',
                    'data': [int(x) for x in df['fulfilled_requests'].tolist()]
                },
                {
                    'label': 'Pending Requests',
                    'data': [int(x) for x in df['pending_requests'].tolist()]
                },
                {
                    'label': 'Cancelled Requests',
                    'data': [int(x) for x in df['cancelled_requests'].tolist()]
                },
                {
                    'label': 'Fulfillment Rate (%)',
                    'data': [float(x) for x in df['fulfillment_rate'].tolist()]
                }
            ]
        }

        return {
            'trends': trends_data,
            'analysis': {
                'request_trend': request_trend,
                'fulfillment_trend': fulfillment_trend,
                'peak_day': peak_idx.strftime('%Y-%m-%d') if hasattr(peak_idx, 'strftime') else str(peak_idx),
                'most_urgent_day': most_urgent_day,
                'blood_type_insights': blood_type_insights,
                'urgency_analysis': {
                    'urgent': urgency_stats['urgent'],
                    'normal': urgency_stats['normal'],
                    'urgent_fulfillment_rate': round(float(urgent_fulfillment_rate), 2)
                }
            }
        }

    @classmethod
    def _generate_donation_trends(cls, parameters):
        """Generate detailed donation trends analysis."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')
        group_by = parameters.get('group_by', 'day')

        # Get base queryset
        donations = DailyDonationStats.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(list(donations.values()))
        
        if df.empty:
            return {
                'trends': {
                    'labels': [],
                    'datasets': []
                },
                'analysis': {
                    'total_trend': 'insufficient_data',
                    'success_rate_trend': 'insufficient_data',
                    'peak_day': None,
                    'lowest_day': None,
                    'blood_type_insights': {}
                }
            }

        # Group by time period if needed
        if group_by == 'week':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('W', on='date').sum()
        elif group_by == 'month':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('M', on='date').sum()

        # Calculate success rates
        df['success_rate'] = (df['successful_donations'] / df['total_donations'] * 100).fillna(0)

        # Calculate trends using simple linear regression
        x = np.arange(len(df))
        
        # Total donations trend
        total_slope, _ = np.polyfit(x, df['total_donations'], 1)
        total_trend = 'increasing' if total_slope > 0.1 else 'decreasing' if total_slope < -0.1 else 'stable'

        # Success rate trend
        success_slope, _ = np.polyfit(x, df['success_rate'], 1)
        success_trend = 'improving' if success_slope > 0.1 else 'declining' if success_slope < -0.1 else 'stable'

        # Find peak and lowest days
        peak_idx = df['total_donations'].idxmax()
        lowest_idx = df['total_donations'].idxmin()

        # Blood type analysis
        blood_type_insights = {}
        for donation in donations:
            breakdown = donation.blood_type_breakdown
            if isinstance(breakdown, str):
                try:
                    breakdown = json.loads(breakdown)
                except json.JSONDecodeError:
                    continue

            for blood_type, data in breakdown.items():
                if blood_types and blood_type not in blood_types:
                    continue
                if blood_type not in blood_type_insights:
                    blood_type_insights[blood_type] = {
                        'total': 0,
                        'successful': 0,
                        'rejected': 0,
                        'success_rate': 0
                    }
                blood_type_insights[blood_type]['total'] += int(data.get('total', 0))
                blood_type_insights[blood_type]['successful'] += int(data.get('successful', 0))
                blood_type_insights[blood_type]['rejected'] += int(data.get('rejected', 0))

        # Calculate success rates for blood types
        for blood_type in blood_type_insights:
            total = blood_type_insights[blood_type]['total']
            if total > 0:
                success_rate = (blood_type_insights[blood_type]['successful'] / total) * 100
                blood_type_insights[blood_type]['success_rate'] = round(float(success_rate), 2)

        # Prepare trend data
        trends_data = {
            'labels': df.index.strftime('%Y-%m-%d').tolist() if hasattr(df.index, 'strftime') else [d.strftime('%Y-%m-%d') for d in df.index],
            'datasets': [
                {
                    'label': 'Total Donations',
                    'data': [int(x) for x in df['total_donations'].tolist()]
                },
                {
                    'label': 'Successful Donations',
                    'data': [int(x) for x in df['successful_donations'].tolist()]
                },
                {
                    'label': 'Rejected Donations',
                    'data': [int(x) for x in df['rejected_donations'].tolist()]
                },
                {
                    'label': 'Success Rate (%)',
                    'data': [float(x) for x in df['success_rate'].tolist()]
                }
            ]
        }

        return {
            'trends': trends_data,
            'analysis': {
                'total_trend': total_trend,
                'success_rate_trend': success_trend,
                'peak_day': peak_idx.strftime('%Y-%m-%d') if hasattr(peak_idx, 'strftime') else str(peak_idx),
                'lowest_day': lowest_idx.strftime('%Y-%m-%d') if hasattr(lowest_idx, 'strftime') else str(lowest_idx),
                'blood_type_insights': blood_type_insights
            }
        }

    @classmethod
    def _generate_inventory_summary(cls, parameters):
        """Generate detailed inventory summary report."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')
        group_by = parameters.get('group_by', 'day')

        # Get base queryset
        snapshots = DailyInventorySnapshot.objects.filter(
            date__range=[start_date, end_date]
        )

        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(list(snapshots.values()))
        
        # Group by time period if needed
        if group_by == 'week':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('W', on='date').last()  # Use last() for snapshots
        elif group_by == 'month':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('M', on='date').last()  # Use last() for snapshots

        # Convert numeric types to Python native types
        def to_native(value):
            if pd.isna(value):
                return 0
            if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
                return int(value)
            if isinstance(value, (np.float64, np.float32)):
                return float(value)
            return value

        # Process inventory levels
        latest_levels = {}
        total_units = 0
        critical_levels = {}
        
        latest_snapshot = snapshots.last()
        if latest_snapshot:
            inventory_levels = latest_snapshot.inventory_levels
            if isinstance(inventory_levels, str):
                try:
                    inventory_levels = json.loads(inventory_levels)
                except json.JSONDecodeError:
                    inventory_levels = {}

            for blood_type, quantity in inventory_levels.items():
                if blood_types and blood_type not in blood_types:
                    continue
                latest_levels[blood_type] = int(quantity)
                total_units += int(quantity)
                if int(quantity) < 5:  # Critical threshold
                    critical_levels[blood_type] = int(quantity)

        # Process expiring units
        expiring_units = {}
        expired_units = {}
        
        for snapshot in snapshots:
            # Process expiring soon
            expiring = snapshot.expiring_soon
            if isinstance(expiring, str):
                try:
                    expiring = json.loads(expiring)
                except json.JSONDecodeError:
                    expiring = {}
                    
            for blood_type, quantity in expiring.items():
                if blood_types and blood_type not in blood_types:
                    continue
                expiring_units[blood_type] = expiring_units.get(blood_type, 0) + int(quantity)

            # Process expired today
            expired = snapshot.expired_today
            if isinstance(expired, str):
                try:
                    expired = json.loads(expired)
                except json.JSONDecodeError:
                    expired = {}
                    
            for blood_type, quantity in expired.items():
                if blood_types and blood_type not in blood_types:
                    continue
                expired_units[blood_type] = expired_units.get(blood_type, 0) + int(quantity)

        # Generate trends data
        trends_data = {
            'labels': df.index.strftime('%Y-%m-%d').tolist() if hasattr(df.index, 'strftime') else [d.strftime('%Y-%m-%d') for d in df.index],
            'datasets': []
        }

        # Add a dataset for each blood type
        all_blood_types = set()
        for snapshot in snapshots:
            inventory_levels = snapshot.inventory_levels
            if isinstance(inventory_levels, str):
                try:
                    inventory_levels = json.loads(inventory_levels)
                except json.JSONDecodeError:
                    continue
            all_blood_types.update(inventory_levels.keys())

        for blood_type in all_blood_types:
            if blood_types and blood_type not in blood_types:
                continue
                
            blood_type_data = []
            for snapshot in snapshots:
                inventory_levels = snapshot.inventory_levels
                if isinstance(inventory_levels, str):
                    try:
                        inventory_levels = json.loads(inventory_levels)
                    except json.JSONDecodeError:
                        inventory_levels = {}
                blood_type_data.append(int(inventory_levels.get(blood_type, 0)))
                
            trends_data['datasets'].append({
                'label': f'{blood_type} Inventory Level',
                'data': blood_type_data
            })

        return {
            'summary': {
                'total_units': total_units,
                'blood_type_levels': latest_levels,
                'critical_levels': critical_levels,
                'total_expiring': sum(expiring_units.values()),
                'total_expired': sum(expired_units.values())
            },
            'trends': trends_data,
            'expiring_breakdown': expiring_units,
            'expired_breakdown': expired_units
        }

    @classmethod
    def _generate_request_summary(cls, parameters):
        """Generate detailed blood request summary report."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')
        group_by = parameters.get('group_by', 'day')

        # Get base queryset
        requests = DailyRequestStats.objects.filter(
            date__range=[start_date, end_date]
        )

        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(list(requests.values()))
        
        # Group by time period if needed
        if group_by == 'week':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('W', on='date').sum()
        elif group_by == 'month':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('M', on='date').sum()

        # Convert numeric types to Python native types
        def to_native(value):
            if pd.isna(value):
                return 0
            if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
                return int(value)
            if isinstance(value, (np.float64, np.float32)):
                return float(value)
            return value

        total_requests = int(df['total_requests'].sum())
        fulfilled_requests = int(df['fulfilled_requests'].sum())
        pending_requests = int(df['pending_requests'].sum())
        cancelled_requests = int(df['cancelled_requests'].sum())
        fulfillment_rate = float(fulfilled_requests / total_requests * 100) if total_requests > 0 else 0.0

        # Process trends data
        trends_data = {
            'labels': df.index.strftime('%Y-%m-%d').tolist() if hasattr(df.index, 'strftime') else [d.strftime('%Y-%m-%d') for d in df.index],
            'total_requests': [to_native(x) for x in df['total_requests'].tolist()],
            'fulfilled_requests': [to_native(x) for x in df['fulfilled_requests'].tolist()],
            'pending_requests': [to_native(x) for x in df['pending_requests'].tolist()],
            'cancelled_requests': [to_native(x) for x in df['cancelled_requests'].tolist()],
        }

        # Aggregate blood type data
        blood_type_data = {}
        urgency_data = {'urgent': 0, 'normal': 0}
        
        for request in requests:
            # Process blood type breakdown
            breakdown = request.blood_type_breakdown
            if isinstance(breakdown, str):
                try:
                    breakdown = json.loads(breakdown)
                except json.JSONDecodeError:
                    continue

            for blood_type, data in breakdown.items():
                if blood_types and blood_type not in blood_types:
                    continue
                if blood_type not in blood_type_data:
                    blood_type_data[blood_type] = {
                        'total': 0,
                        'fulfilled': 0,
                        'pending': 0,
                        'cancelled': 0
                    }
                blood_type_data[blood_type]['total'] += int(data.get('total', 0))
                blood_type_data[blood_type]['fulfilled'] += int(data.get('fulfilled', 0))
                blood_type_data[blood_type]['pending'] += int(data.get('pending', 0))
                blood_type_data[blood_type]['cancelled'] += int(data.get('cancelled', 0))

            # Process urgency breakdown
            urgency = request.urgency_breakdown
            if isinstance(urgency, str):
                try:
                    urgency = json.loads(urgency)
                except json.JSONDecodeError:
                    continue
                    
            urgency_data['urgent'] += int(urgency.get('urgent', 0))
            urgency_data['normal'] += int(urgency.get('normal', 0))

        return {
            'summary': {
                'total_requests': total_requests,
                'fulfilled_requests': fulfilled_requests,
                'pending_requests': pending_requests,
                'cancelled_requests': cancelled_requests,
                'fulfillment_rate': fulfillment_rate,
            },
            'trends': trends_data,
            'blood_type_breakdown': blood_type_data,
            'urgency_breakdown': urgency_data
        }

    @classmethod
    def _generate_donation_summary(cls, parameters):
        """Generate detailed donation summary report."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')
        group_by = parameters.get('group_by', 'day')

        # Get base queryset with selected fields
        donations = DailyDonationStats.objects.filter(
            date__range=[start_date, end_date]
        ).values('date', 'total_donations', 'successful_donations', 'rejected_donations', 'blood_type_breakdown')

        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(list(donations))
        
        if df.empty:
            return {
                'summary': {
                    'total_donations': 0,
                    'successful_donations': 0,
                    'rejected_donations': 0,
                    'success_rate': 0.0,
                },
                'trends': {
                    'labels': [],
                    'total_donations': [],
                    'successful_donations': [],
                    'rejected_donations': [],
                },
                'blood_type_breakdown': {}
            }

        # Ensure required columns exist with default values
        required_columns = ['total_donations', 'successful_donations', 'rejected_donations']
        for col in required_columns:
            if col not in df.columns:
                df[col] = 0

        # Group by time period if needed
        if group_by == 'week':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('W', on='date').sum()
        elif group_by == 'month':
            df['date'] = pd.to_datetime(df['date'])
            df = df.resample('M', on='date').sum()

        # Convert numeric types to Python native types
        def to_native(value):
            if pd.isna(value):
                return 0
            if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
                return int(value)
            if isinstance(value, (np.float64, np.float32)):
                return float(value)
            return value

        # Calculate summary statistics
        total_count = to_native(df['total_donations'].sum())
        successful_count = to_native(df['successful_donations'].sum())
        rejected_count = to_native(df['rejected_donations'].sum())
        success_rate = float(successful_count / total_count * 100) if total_count > 0 else 0.0

        # Convert dates to strings and values to native Python types
        trends_data = {
            'labels': df.index.strftime('%Y-%m-%d').tolist() if hasattr(df.index, 'strftime') else [d.strftime('%Y-%m-%d') for d in df.index],
            'total_donations': [to_native(x) for x in df['total_donations'].tolist()],
            'successful_donations': [to_native(x) for x in df['successful_donations'].tolist()],
            'rejected_donations': [to_native(x) for x in df['rejected_donations'].tolist()],
        }

        return {
            'summary': {
                'total_donations': total_count,
                'successful_donations': successful_count,
                'rejected_donations': rejected_count,
                'success_rate': success_rate,
            },
            'trends': trends_data,
            'blood_type_breakdown': cls._aggregate_blood_type_data(donations, blood_types)
        }

    @classmethod
    def _generate_inventory_forecast(cls, parameters):
        """Generate inventory forecast using time series analysis."""
        start_date = parameters['start_date']
        end_date = parameters['end_date']
        blood_types = parameters.get('blood_types')

        # Get historical data
        snapshots = DailyInventorySnapshot.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        forecast_data = {}
        for blood_type in blood_types or cls._get_all_blood_types():
            # Extract time series for this blood type
            levels = [snap.inventory_levels.get(blood_type, 0) for snap in snapshots]
            dates = [snap.date for snap in snapshots]
            
            # Create time series and resample to daily frequency
            ts = pd.Series(levels, index=dates)
            ts = ts.resample('D').ffill()

            # Calculate trend
            trend = np.polyfit(range(len(ts)), ts.values, 1)
            forecast = np.poly1d(trend)
            
            # Generate 7-day forecast
            future_dates = pd.date_range(end_date + timedelta(days=1), periods=7)
            future_values = forecast(range(len(ts), len(ts) + 7))

            forecast_data[blood_type] = {
                'historical': {
                    'dates': ts.index.strftime('%Y-%m-%d').tolist(),
                    'values': ts.values.tolist()
                },
                'forecast': {
                    'dates': future_dates.strftime('%Y-%m-%d').tolist(),
                    'values': future_values.tolist()
                },
                'trend': {
                    'slope': float(trend[0]),
                    'intercept': float(trend[1])
                }
            }

        return forecast_data

    @classmethod
    def export_report(cls, data, format='json'):
        """Export report data in specified format."""
        if format == 'json':
            return data
        elif format == 'excel':
            return cls._export_to_excel(data)
        elif format == 'pdf':
            return cls._export_to_pdf(data)
        else:
            raise ValueError(f"Unsupported format: {format}")

    @staticmethod
    def _export_to_excel(data):
        """Export report data to Excel format."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Report"

        # Add headers
        headers = list(data['summary'].keys())
        ws.append(['Metric', 'Value'])
        
        # Add summary data
        for metric, value in data['summary'].items():
            ws.append([metric, value])

        # Add trends data if present
        if 'trends' in data:
            ws = wb.create_sheet("Trends")
            headers = ['Date'] + list(data['trends'].keys())
            ws.append(headers)
            
            for i in range(len(data['trends']['labels'])):
                row = [data['trends']['labels'][i]]
                for key in headers[1:]:
                    row.append(data['trends'][key][i])
                ws.append(row)

        return wb

    @staticmethod
    def _export_to_pdf(data):
        """Export report data to PDF format."""
        doc = SimpleDocTemplate("report.pdf", pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()

        # Add title
        elements.append(Paragraph("Analytics Report", styles['Title']))
        
        # Add summary table
        summary_data = [['Metric', 'Value']]
        for metric, value in data['summary'].items():
            summary_data.append([metric, str(value)])

        summary_table = Table(summary_data)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)

        return doc

    @classmethod
    def _get_cache_key(cls, report_type, parameters):
        """Generate a unique cache key for the report."""
        param_str = '_'.join(f"{k}:{v}" for k, v in sorted(parameters.items()))
        return f"{cls.CACHE_PREFIX}{report_type}_{param_str}"

    @classmethod
    def _acquire_generation_lock(cls, cache_key):
        """Try to acquire a lock for report generation."""
        return cache.add(f"{cache_key}_lock", True, timeout=300)  # 5-minute timeout

    @classmethod
    def _release_generation_lock(cls, cache_key):
        """Release the report generation lock."""
        cache.delete(f"{cache_key}_lock")

    @classmethod
    def _cache_report(cls, report_type, parameters, data):
        """Cache the generated report."""
        # Convert dates in parameters to strings
        processed_params = parameters.copy()
        if 'start_date' in processed_params:
            processed_params['start_date'] = processed_params['start_date'].isoformat()
        if 'end_date' in processed_params:
            processed_params['end_date'] = processed_params['end_date'].isoformat()
        
        # Convert any date objects in data to strings
        processed_data = cls._process_dates_in_data(data)
        
        ReportCache.objects.create(
            report_type=report_type,
            parameters=processed_params,
            data=processed_data,
            expires_at=timezone.now() + cls.CACHE_DURATION
        )

    @staticmethod
    def _aggregate_blood_type_data(donations_qs, blood_types=None):
        """Aggregate blood type data from queryset."""
        all_data = {}
        for donation in donations_qs:
            blood_type_data = donation.blood_type_breakdown
            # Handle both string and dict data formats
            if isinstance(blood_type_data, str):
                try:
                    blood_type_data = json.loads(blood_type_data)
                except json.JSONDecodeError:
                    continue

            for blood_type, data in blood_type_data.items():
                if blood_types and blood_type not in blood_types:
                    continue
                if blood_type not in all_data:
                    all_data[blood_type] = {
                        'total': 0,
                        'successful': 0,
                        'rejected': 0
                    }
                # Ensure we're adding integers
                all_data[blood_type]['total'] += int(data.get('total', 0))
                all_data[blood_type]['successful'] += int(data.get('successful', 0))
                all_data[blood_type]['rejected'] += int(data.get('rejected', 0))
        return all_data

    @staticmethod
    def _get_all_blood_types():
        """Get list of all blood types."""
        return [bg[0] for bg in Donation.BLOOD_GROUP_CHOICES]

    @classmethod
    def _process_dates_in_data(cls, data):
        """Recursively process data structure and convert dates to ISO format strings."""
        if isinstance(data, (datetime, timezone.datetime)):
            return data.isoformat()
        elif isinstance(data, dict):
            return {key: cls._process_dates_in_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [cls._process_dates_in_data(item) for item in data]
        elif isinstance(data, (pd.Timestamp, pd.DatetimeIndex)):
            return data.strftime('%Y-%m-%d')
        return data


class ChartService:
    @classmethod
    def generate_donation_trend_chart(cls, start_date, end_date, blood_types=None):
        """Generate donation trend chart data."""
        donations = DailyDonationStats.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        data = {
            'labels': [d.date.strftime('%Y-%m-%d') for d in donations],
            'datasets': [
                {
                    'label': 'Total Donations',
                    'data': [d.total_donations for d in donations],
                    'borderColor': '#4CAF50',
                    'fill': False
                },
                {
                    'label': 'Successful Donations',
                    'data': [d.successful_donations for d in donations],
                    'borderColor': '#2196F3',
                    'fill': False
                },
                {
                    'label': 'Rejected Donations',
                    'data': [d.rejected_donations for d in donations],
                    'borderColor': '#F44336',
                    'fill': False
                }
            ],
            'title': 'Donation Trends',
            'type': 'line'
        }
        return data

    @classmethod
    def generate_blood_type_distribution_chart(cls, date=None):
        """Generate blood type distribution chart data."""
        if date is None:
            date = timezone.now().date()

        snapshot = DailyInventorySnapshot.objects.filter(date=date).first()
        if not snapshot:
            # Return empty chart data structure
            return {
                'labels': [],
                'datasets': [],
                'title': 'Blood Type Distribution (No Data)',
                'type': 'doughnut'
            }

        labels = []
        data = []
        colors = [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
            '#9966FF', '#FF9F40', '#FF6384', '#36A2EB'
        ]

        try:
            inventory_levels = snapshot.inventory_levels
            if isinstance(inventory_levels, str):
                inventory_levels = json.loads(inventory_levels)
                
            for blood_type, level in inventory_levels.items():
                labels.append(blood_type)
                data.append(int(level))
        except (AttributeError, json.JSONDecodeError, TypeError):
            # Return empty chart data structure on error
            return {
                'labels': [],
                'datasets': [{
                    'data': [],
                    'backgroundColor': [],
                    'label': 'Blood Type Distribution'
                }],
                'title': 'Blood Type Distribution (Error)',
                'type': 'doughnut'
            }

        return {
            'labels': labels,
            'datasets': [{
                'data': data,
                'backgroundColor': colors[:len(labels)],
                'label': 'Blood Type Distribution'
            }],
            'title': f'Blood Type Distribution ({date})',
            'type': 'doughnut'
        }

    @classmethod
    def generate_requests_fulfillment_chart(cls, start_date, end_date):
        """Generate requests fulfillment chart data."""
        requests = DailyRequestStats.objects.filter(
            date__range=[start_date, end_date]
        )

        total = sum(r.total_requests for r in requests)
        fulfilled = sum(r.fulfilled_requests for r in requests)
        pending = sum(r.pending_requests for r in requests)
        cancelled = sum(r.cancelled_requests for r in requests)

        return {
            'labels': ['Fulfilled', 'Pending', 'Cancelled'],
            'datasets': [{
                'data': [fulfilled, pending, cancelled],
                'backgroundColor': ['#4CAF50', '#FFC107', '#F44336'],
                'label': 'Request Status Distribution'
            }],
            'title': 'Blood Request Fulfillment',
            'type': 'pie'
        }

    @classmethod
    def generate_inventory_forecast_chart(cls, blood_type, days=30):
        """Generate inventory forecast chart."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        snapshots = DailyInventorySnapshot.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        dates = []
        levels = []
        
        # Process snapshots and handle potential JSON strings
        for snapshot in snapshots:
            try:
                inventory_levels = snapshot.inventory_levels
                if isinstance(inventory_levels, str):
                    inventory_levels = json.loads(inventory_levels)
                level = int(inventory_levels.get(blood_type, 0))
                dates.append(snapshot.date.strftime('%Y-%m-%d'))
                levels.append(level)
            except (json.JSONDecodeError, AttributeError, ValueError, TypeError):
                continue

        # If no data is available, return empty chart structure
        if not dates:
            today = timezone.now().date()
            empty_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
            return {
                'labels': empty_dates,
                'datasets': [
                    {
                        'label': f'Actual {blood_type} Inventory',
                        'data': [0] * 7,
                        'borderColor': '#2196F3',
                        'fill': False
                    },
                    {
                        'label': f'Forecast {blood_type} Inventory',
                        'data': [0] * 7,
                        'borderColor': '#FF9800',
                        'borderDash': [5, 5],
                        'fill': False
                    }
                ],
                'title': f'Inventory Forecast - {blood_type} (No Historical Data)',
                'type': 'line'
            }

        try:
            # Calculate trend line using numpy
            x = np.arange(len(dates))
            y = np.array(levels)
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)

            # Generate forecast points
            forecast_x = np.arange(len(dates), len(dates) + 7)  # 7 days forecast
            forecast_y = p(forecast_x)
            
            # Add forecast dates
            last_date = datetime.strptime(dates[-1], '%Y-%m-%d')
            for i in range(1, 8):
                forecast_date = last_date + timedelta(days=i)
                dates.append(forecast_date.strftime('%Y-%m-%d'))

            return {
                'labels': dates,
                'datasets': [
                    {
                        'label': f'Actual {blood_type} Inventory',
                        'data': levels + [None] * 7,  # Pad with nulls for forecast period
                        'borderColor': '#2196F3',
                        'fill': False
                    },
                    {
                        'label': f'Forecast {blood_type} Inventory',
                        'data': [None] * len(levels) + forecast_y.tolist(),  # Pad with nulls for historical period
                        'borderColor': '#FF9800',
                        'borderDash': [5, 5],
                        'fill': False
                    }
                ],
                'title': f'Inventory Forecast - {blood_type}',
                'type': 'line'
            }
        except Exception as e:
            # If forecasting fails, return just the historical data
            return {
                'labels': dates,
                'datasets': [
                    {
                        'label': f'Actual {blood_type} Inventory',
                        'data': levels,
                        'borderColor': '#2196F3',
                        'fill': False
                    }
                ],
                'title': f'Inventory Data - {blood_type} (Forecast Unavailable)',
                'type': 'line'
            }