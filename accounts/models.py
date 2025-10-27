from django.contrib.auth.models import AbstractUser
from django.db import models


BLOOD_GROUP_CHOICES = [
    ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
    ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
]

ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('donor', 'Donor'),
]


class User(AbstractUser):
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='donor')
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=100, null=True, blank=True)
    email_verified = models.BooleanField(default=False)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_donor(self):
        return self.role == 'donor'
