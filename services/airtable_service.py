from pyairtable import Api
from django.conf import settings
import os

class AirtableService:
    def __init__(self):
        self.api_key = os.getenv('AIRTABLE_API_KEY')
        self.base_id = os.getenv('AIRTABLE_BASE_ID')
        self.api = Api(self.api_key)

    def get_table(self, table_name):
        return self.api.table(self.base_id, table_name)

    # Inventory Methods
    def get_inventory(self):
        table = self.get_table('Inventory')
        return table.all()

    def update_inventory(self, record_id, fields):
        table = self.get_table('Inventory')
        return table.update(record_id, fields)

    def create_inventory_record(self, fields):
        table = self.get_table('Inventory')
        return table.create(fields)

    # Donations Methods
    def get_donations(self):
        table = self.get_table('Donations')
        return table.all()

    def create_donation(self, fields):
        table = self.get_table('Donations')
        return table.create(fields)

    # Blood Requests Methods
    def get_blood_requests(self):
        table = self.get_table('BloodRequests')
        return table.all()

    def create_blood_request(self, fields):
        table = self.get_table('BloodRequests')
        return table.create(fields)

    def update_blood_request(self, record_id, fields):
        table = self.get_table('BloodRequests')
        return table.update(record_id, fields)

    # Analytics Methods
    def get_analytics_data(self, table_name, formula=None):
        table = self.get_table(table_name)
        return table.all(formula=formula)

    def get_inventory_by_blood_type(self):
        table = self.get_table('Inventory')
        return table.all(view='BloodTypeView')