from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from accounts.utils import success_response, error_response
from .models import Inventory, Donation, BloodRequest, InventoryTransaction
from .serializers import (
    InventorySerializer,
    DonationSerializer,
    DonationAdminSerializer,
    BloodRequestSerializer,
    BloodRequestActionSerializer,
    InventoryTransactionSerializer
)


class InventoryListView(generics.ListAPIView):
    """List all blood group inventory levels"""
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            "Inventory levels retrieved successfully",
            data=serializer.data
        )


class DonationCreateView(generics.CreateAPIView):
    """Create a new donation request (donor only)"""
    serializer_class = DonationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response(
                "Donation request created successfully",
                data=serializer.data,
                status_code=status.HTTP_201_CREATED
            )
        return error_response(
            "Unable to create donation request",
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class DonationListView(generics.ListAPIView):
    """List donations with filtering"""
    serializer_class = DonationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Donation.objects.all()

        if not user.is_admin:
            # Donors see only their own donations
            queryset = queryset.filter(donor=user)

        # Filter by status if provided
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(request_date__range=[start_date, end_date])

        return queryset.order_by('-request_date')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            "Donations retrieved successfully",
            data=serializer.data
        )


class DonationDetailView(generics.RetrieveAPIView):
    """Retrieve a specific donation"""
    serializer_class = DonationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin:
            return Donation.objects.all()
        return Donation.objects.filter(donor=user)

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return success_response(
                "Donation details retrieved successfully",
                data=serializer.data
            )
        except Donation.DoesNotExist:
            return error_response(
                "Donation not found",
                status_code=status.HTTP_404_NOT_FOUND
            )


class DonationActionView(generics.UpdateAPIView):
    """Approve or reject a donation (admin only)"""
    serializer_class = DonationAdminSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Donation.objects.all()

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.is_admin:
            raise permissions.PermissionDenied("Only admins can approve/reject donations")
        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            try:
                if request.data.get('status') == 'approved':
                    instance.approve(notes=request.data.get('notes', ''))
                else:
                    instance.reject(notes=request.data.get('notes', ''))

                return success_response(
                    f"Donation {instance.status} successfully",
                    data=serializer.data
                )
            except ValueError as e:
                return error_response(
                    str(e),
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        return error_response(
            "Invalid data provided",
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class BloodRequestCreateView(generics.CreateAPIView):
    """Create a new blood request (admin only)"""
    serializer_class = BloodRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response(
                "Blood request created successfully",
                data=serializer.data,
                status_code=status.HTTP_201_CREATED
            )
        return error_response(
            "Unable to create blood request",
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class BloodRequestListView(generics.ListAPIView):
    """List blood requests (admin only)"""
    serializer_class = BloodRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = BloodRequest.objects.all()

    def get_queryset(self):
        if not self.request.user.is_admin:
            raise permissions.PermissionDenied("Only admins can view blood requests")

        queryset = BloodRequest.objects.all()

        # Filter by status if provided
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Filter by urgency
        urgency = self.request.query_params.get('urgency')
        if urgency:
            queryset = queryset.filter(urgency=urgency.lower() == 'true')

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(request_date__range=[start_date, end_date])

        return queryset.order_by('-urgency', '-request_date')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            "Blood requests retrieved successfully",
            data=serializer.data
        )


class BloodRequestDetailView(generics.RetrieveAPIView):
    """Retrieve a specific blood request (admin only)"""
    serializer_class = BloodRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = BloodRequest.objects.all()

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.is_admin:
            raise permissions.PermissionDenied("Only admins can view blood requests")
        return obj

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return success_response(
                "Blood request details retrieved successfully",
                data=serializer.data
            )
        except BloodRequest.DoesNotExist:
            return error_response(
                "Blood request not found",
                status_code=status.HTTP_404_NOT_FOUND
            )


class BloodRequestActionView(generics.UpdateAPIView):
    """Fulfill or deny a blood request (admin only)"""
    serializer_class = BloodRequestActionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = BloodRequest.objects.all()

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.is_admin:
            raise permissions.PermissionDenied("Only admins can fulfill/deny requests")
        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            try:
                if request.data.get('status') == 'fulfilled':
                    instance.fulfill(notes=request.data.get('notes', ''))
                else:
                    instance.deny(notes=request.data.get('notes', ''))

                return success_response(
                    f"Blood request {instance.status} successfully",
                    data=serializer.data
                )
            except ValueError as e:
                return error_response(
                    str(e),
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        return error_response(
            "Invalid data provided",
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class DashboardView(generics.GenericAPIView):
    """Dashboard data for admins"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return error_response(
                "Only admins can access dashboard data",
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Get inventory status
        inventory = Inventory.objects.all()
        inventory_serializer = InventorySerializer(inventory, many=True)

        # Get pending counts
        pending_donations = Donation.objects.filter(status='pending').count()
        pending_requests = BloodRequest.objects.filter(status='pending').count()

        # Get today's activity
        today = timezone.now().date()
        today_donations = Donation.objects.filter(
            action_date__date=today,
            status='approved'
        ).count()
        today_requests = BloodRequest.objects.filter(
            action_date__date=today,
            status='fulfilled'
        ).count()

        # Get recent transactions
        recent_transactions = InventoryTransaction.objects.all()[:10]
        transaction_serializer = InventoryTransactionSerializer(recent_transactions, many=True)

        # Get low stock alerts
        low_stock = Inventory.objects.filter(is_low=True)
        low_stock_serializer = InventorySerializer(low_stock, many=True)

        data = {
            'inventory': inventory_serializer.data,
            'pending': {
                'donations': pending_donations,
                'requests': pending_requests
            },
            'today': {
                'donations': today_donations,
                'requests': today_requests
            },
            'recent_transactions': transaction_serializer.data,
            'low_stock_alerts': low_stock_serializer.data
        }

        return success_response(
            "Dashboard data retrieved successfully",
            data=data
        )
