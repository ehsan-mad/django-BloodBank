import os
import django
from datetime import datetime
from pyairtable import Api
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blood_management.settings')
django.setup()

# Import models after Django setup
from donations.models import Donation
from analytics.models import BloodRequest, Inventory

class DataMigrator:
    def __init__(self):
        self.api_key = os.getenv('AIRTABLE_API_KEY')
        self.base_id = os.getenv('AIRTABLE_BASE_ID')
        self.api = Api(self.api_key)

    def get_table(self, table_name):
        return self.api.table(self.base_id, table_name)

    def migrate_inventory(self):
        print("Migrating Inventory data...")
        inventory_table = self.get_table('Inventory')
        inventory_records = Inventory.objects.all()

        for record in inventory_records:
            fields = {
                'blood_type': record.blood_type,
                'units': record.units,
                'expiry_date': record.expiry_date.isoformat() if record.expiry_date else None,
                'location': record.location,
                'status': record.status,
                'created_at': record.created_at.isoformat() if record.created_at else None,
                'updated_at': record.updated_at.isoformat() if record.updated_at else None
            }
            try:
                inventory_table.create(fields)
                print(f"Created inventory record for {record.blood_type}")
            except Exception as e:
                print(f"Error creating inventory record: {e}")

    def migrate_donations(self):
        print("Migrating Donations data...")
        donations_table = self.get_table('Donations')
        donation_records = Donation.objects.all()

        for record in donation_records:
            fields = {
                'donor_name': f"{record.donor.first_name} {record.donor.last_name}" if record.donor else "Anonymous",
                'blood_type': record.blood_type,
                'donation_date': record.donation_date.isoformat() if record.donation_date else None,
                'units': record.units,
                'status': record.status,
                'created_at': record.created_at.isoformat() if record.created_at else None
            }
            try:
                donations_table.create(fields)
                print(f"Created donation record for {fields['donor_name']}")
            except Exception as e:
                print(f"Error creating donation record: {e}")

    def migrate_blood_requests(self):
        print("Migrating Blood Requests data...")
        requests_table = self.get_table('BloodRequests')
        request_records = BloodRequest.objects.all()

        for record in request_records:
            fields = {
                'patient_name': record.patient_name,
                'blood_type': record.blood_type,
                'request_date': record.request_date.isoformat() if record.request_date else None,
                'units_needed': record.units_needed,
                'urgency': record.urgency,
                'status': record.status,
                'created_at': record.created_at.isoformat() if record.created_at else None
            }
            try:
                requests_table.create(fields)
                print(f"Created blood request record for {record.patient_name}")
            except Exception as e:
                print(f"Error creating blood request record: {e}")

def main():
    print("Starting data migration to Airtable...")
    
    # Check for environment variables
    if not os.getenv('AIRTABLE_API_KEY') or not os.getenv('AIRTABLE_BASE_ID'):
        print("Error: AIRTABLE_API_KEY and AIRTABLE_BASE_ID environment variables must be set")
        return

    migrator = DataMigrator()

    # Perform migrations
    try:
        migrator.migrate_inventory()
        migrator.migrate_donations()
        migrator.migrate_blood_requests()
        print("Data migration completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == '__main__':
    main()