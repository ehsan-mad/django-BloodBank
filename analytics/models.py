from django.db import models
from django.utils import timezone


class DailyDonationStats(models.Model):
    """Daily aggregated statistics about blood donations."""
    date = models.DateField(unique=True)
    total_donations = models.IntegerField(default=0)
    successful_donations = models.IntegerField(default=0)
    rejected_donations = models.IntegerField(default=0)
    blood_type_breakdown = models.JSONField(default=dict)  # {'A+': 5, 'B+': 3, ...}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Daily Donation Statistics'
        verbose_name_plural = 'Daily Donation Statistics'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
        ]

    def __str__(self):
        return f"Donation Stats for {self.date}"


class DailyRequestStats(models.Model):
    """Daily aggregated statistics about blood requests."""
    date = models.DateField(unique=True)
    total_requests = models.IntegerField(default=0)
    fulfilled_requests = models.IntegerField(default=0)
    pending_requests = models.IntegerField(default=0)
    cancelled_requests = models.IntegerField(default=0)
    blood_type_breakdown = models.JSONField(default=dict)  # {'A+': 5, 'B+': 3, ...}
    urgency_breakdown = models.JSONField(default=dict)  # {'urgent': 5, 'normal': 3}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Daily Request Statistics'
        verbose_name_plural = 'Daily Request Statistics'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
        ]

    def __str__(self):
        return f"Request Stats for {self.date}"


class DailyInventorySnapshot(models.Model):
    """Daily snapshot of blood inventory levels."""
    date = models.DateField(unique=True)
    inventory_levels = models.JSONField(default=dict)  # {'A+': 500, 'B+': 300, ...} (in ml)
    expiring_soon = models.JSONField(default=dict)  # {'A+': 100, 'B+': 50, ...} (expires in 7 days)
    expired_today = models.JSONField(default=dict)  # {'A+': 0, 'B+': 50, ...} (expired on this date)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Daily Inventory Snapshot'
        verbose_name_plural = 'Daily Inventory Snapshots'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
        ]

    def __str__(self):
        return f"Inventory Snapshot for {self.date}"


class ReportCache(models.Model):
    """Cache for generated reports to avoid regenerating frequently accessed reports."""
    report_type = models.CharField(max_length=50)  # e.g., 'monthly_donation_report', 'inventory_forecast'
    parameters = models.JSONField()  # Report parameters used to generate this cache
    data = models.JSONField()  # The actual report data
    file_path = models.CharField(max_length=255, null=True, blank=True)  # Path to exported file if any
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_generating = models.BooleanField(default=False)  # Lock to prevent duplicate generation
    
    class Meta:
        verbose_name = 'Report Cache'
        verbose_name_plural = 'Report Caches'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', '-created_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.report_type} - {self.created_at}"

    def is_expired(self):
        """Check if the cache has expired."""
        return timezone.now() > self.expires_at
