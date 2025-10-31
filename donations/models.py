from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.conf import settings
from accounts.models import BLOOD_GROUP_CHOICES


class Inventory(models.Model):
    """Tracks current blood bag inventory per blood group"""
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, unique=True)
    quantity = models.PositiveIntegerField(default=0)
    is_low = models.BooleanField(default=False)  # True when quantity < 5
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.blood_group}: {self.quantity} bags"

    def check_low_stock(self):
        """Update is_low flag based on quantity"""
        self.is_low = self.quantity < 5
        self.save(update_fields=['is_low'])

    class Meta:
        verbose_name_plural = "Inventories"


class Donation(models.Model):
    """Blood donation requests from donors"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ]

    donor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    request_date = models.DateTimeField(auto_now_add=True)
    action_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Donation by {self.donor.username} ({self.blood_group})"

    def approve(self, notes=""):
        """Approve donation and update inventory"""
        if self.status != 'pending':
            raise ValueError("Can only approve pending donations")
        
        inventory = Inventory.objects.get_or_create(blood_group=self.blood_group)[0]
        inventory.quantity += self.quantity
        inventory.save()
        inventory.check_low_stock()

        self.status = 'approved'
        self.action_date = timezone.now()
        self.notes = notes
        self.save()

        # Log the transaction
        InventoryTransaction.objects.create(
            inventory=inventory,
            transaction_type='donation',
            quantity=self.quantity,
            blood_group=self.blood_group,
            reference_id=self.id
        )

    def reject(self, notes):
        """Reject donation request"""
        if self.status != 'pending':
            raise ValueError("Can only reject pending donations")
        
        self.status = 'rejected'
        self.action_date = timezone.now()
        self.notes = notes
        self.save()


class BloodRequest(models.Model):
    """Blood request from hospital/admin"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('fulfilled', 'Fulfilled'),
        ('denied', 'Denied')
    ]

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    patient_name = models.CharField(max_length=100)
    hospital = models.CharField(max_length=200)
    urgency = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    request_date = models.DateTimeField(auto_now_add=True)
    action_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Request for {self.quantity} bags of {self.blood_group}"

    def fulfill(self, notes=""):
        """Fulfill blood request and update inventory"""
        if self.status != 'pending':
            raise ValueError("Can only fulfill pending requests")
        
        inventory = Inventory.objects.get(blood_group=self.blood_group)
        if inventory.quantity < self.quantity:
            raise ValueError("Insufficient inventory")

        inventory.quantity -= self.quantity
        inventory.save()
        inventory.check_low_stock()

        self.status = 'fulfilled'
        self.action_date = timezone.now()
        self.notes = notes
        self.save()

        # Log the transaction
        InventoryTransaction.objects.create(
            inventory=inventory,
            transaction_type='request',
            quantity=-self.quantity,  # Negative for requests
            blood_group=self.blood_group,
            reference_id=self.id
        )

    def deny(self, notes):
        """Deny blood request"""
        if self.status != 'pending':
            raise ValueError("Can only deny pending requests")
        
        self.status = 'denied'
        self.action_date = timezone.now()
        self.notes = notes
        self.save()


class InventoryTransaction(models.Model):
    """Audit log for all inventory changes"""
    TRANSACTION_TYPES = [
        ('donation', 'Donation'),
        ('request', 'Blood Request'),
        ('adjustment', 'Manual Adjustment')
    ]

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Can be negative for requests
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES)
    reference_id = models.IntegerField(null=True, blank=True)  # ID of related Donation/Request
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.quantity} of {self.blood_group}"

    class Meta:
        ordering = ['-timestamp']
