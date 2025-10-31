from django.contrib import admin
from .models import Inventory, Donation, BloodRequest, InventoryTransaction


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('blood_group', 'quantity', 'is_low', 'last_updated')
    list_filter = ('is_low', 'blood_group')
    search_fields = ('blood_group',)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ('donor', 'blood_group', 'quantity', 'status', 'request_date', 'action_date')
    list_filter = ('status', 'blood_group', 'request_date')
    search_fields = ('donor__username', 'donor__email', 'blood_group')
    readonly_fields = ('request_date',)


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ('requested_by', 'blood_group', 'quantity', 'hospital', 'urgency', 
                   'status', 'request_date', 'action_date')
    list_filter = ('status', 'blood_group', 'urgency', 'request_date')
    search_fields = ('patient_name', 'hospital', 'requested_by__username')
    readonly_fields = ('request_date',)


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_type', 'blood_group', 'quantity', 'timestamp')
    list_filter = ('transaction_type', 'blood_group', 'timestamp')
    search_fields = ('blood_group', 'notes')
    readonly_fields = ('timestamp',)
