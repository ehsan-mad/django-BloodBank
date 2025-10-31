from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import Inventory, Donation, BloodRequest, InventoryTransaction


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ['blood_group', 'quantity', 'is_low', 'last_updated']
        read_only_fields = ['is_low', 'last_updated']


class DonationSerializer(serializers.ModelSerializer):
    donor_name = serializers.CharField(source='donor.username', read_only=True)

    class Meta:
        model = Donation
        fields = ['id', 'donor', 'donor_name', 'blood_group', 'quantity', 
                 'status', 'request_date', 'action_date', 'notes']
        read_only_fields = ['donor', 'status', 'request_date', 'action_date']

    def validate(self, data):
        """
        Check if donor has a pending or recent approved donation
        """
        donor = self.context['request'].user
        if not donor.is_donor:
            raise serializers.ValidationError("Only donors can create donation requests")

        # Check recent approved donations (90 days cooling period)
        ninety_days_ago = timezone.now() - timedelta(days=90)
        recent_donation = Donation.objects.filter(
            donor=donor,
            status='approved',
            action_date__gt=ninety_days_ago
        ).first()

        if recent_donation:
            days_remaining = 90 - (timezone.now() - recent_donation.action_date).days
            raise serializers.ValidationError(
                f"You must wait {days_remaining} more days before donating again"
            )

        # Check pending donations
        pending_donation = Donation.objects.filter(
            donor=donor,
            status='pending'
        ).first()

        if pending_donation:
            raise serializers.ValidationError(
                "You already have a pending donation request"
            )

        return data

    def create(self, validated_data):
        # Set donor to current user
        validated_data['donor'] = self.context['request'].user
        return super().create(validated_data)


class DonationAdminSerializer(serializers.ModelSerializer):
    """Serializer for admin actions on donations"""
    donor_name = serializers.CharField(source='donor.username', read_only=True)

    class Meta:
        model = Donation
        fields = ['id', 'donor', 'donor_name', 'blood_group', 'quantity', 
                 'status', 'request_date', 'action_date', 'notes']
        read_only_fields = ['donor', 'blood_group', 'quantity', 'request_date']

    def validate_status(self, value):
        """Ensure status transitions are valid"""
        if self.instance.status != 'pending':
            raise serializers.ValidationError(
                "Only pending donations can be approved or rejected"
            )
        if value not in ['approved', 'rejected']:
            raise serializers.ValidationError(
                "Status must be either 'approved' or 'rejected'"
            )
        return value

    def validate(self, data):
        """Ensure admin is making the change"""
        if not self.context['request'].user.is_admin:
            raise serializers.ValidationError("Only admins can approve or reject donations")
        return data


class BloodRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.username', read_only=True)

    class Meta:
        model = BloodRequest
        fields = ['id', 'requested_by', 'requested_by_name', 'blood_group', 'quantity',
                 'patient_name', 'hospital', 'urgency', 'status', 'request_date',
                 'action_date', 'notes']
        read_only_fields = ['requested_by', 'status', 'request_date', 'action_date']

    def validate(self, data):
        if not self.context['request'].user.is_admin:
            raise serializers.ValidationError("Only admins can create blood requests")
        return data

    def create(self, validated_data):
        validated_data['requested_by'] = self.context['request'].user
        return super().create(validated_data)


class BloodRequestActionSerializer(BloodRequestSerializer):
    """Serializer for fulfilling or denying requests"""
    class Meta(BloodRequestSerializer.Meta):
        read_only_fields = ['requested_by', 'blood_group', 'quantity', 'patient_name',
                           'hospital', 'urgency', 'request_date']

    def validate_status(self, value):
        if self.instance.status != 'pending':
            raise serializers.ValidationError(
                "Only pending requests can be fulfilled or denied"
            )
        if value not in ['fulfilled', 'denied']:
            raise serializers.ValidationError(
                "Status must be either 'fulfilled' or 'denied'"
            )

        if value == 'fulfilled':
            # Check if we have enough inventory
            try:
                inventory = Inventory.objects.get(blood_group=self.instance.blood_group)
                if inventory.quantity < self.instance.quantity:
                    raise serializers.ValidationError(
                        f"Insufficient inventory. Available: {inventory.quantity} bags"
                    )
            except Inventory.DoesNotExist:
                raise serializers.ValidationError("No inventory for this blood group")

        return value


class InventoryTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryTransaction
        fields = ['id', 'transaction_type', 'quantity', 'blood_group',
                 'reference_id', 'timestamp', 'notes']
        read_only_fields = fields  # All fields read-only - created by donation/request actions