from django.conf import settings
from django.core import signing
from django.urls import reverse

SIGNING_SALT = 'email-verification'


def make_verification_token(user):
    data = {'user_id': user.id}
    token = signing.dumps(data, key=settings.SECRET_KEY, salt=SIGNING_SALT)
    return token


def verify_verification_token(token, max_age=60 * 60 * 24):
    try:
        data = signing.loads(token, key=settings.SECRET_KEY, salt=SIGNING_SALT, max_age=max_age)
        return data
    except signing.BadSignature:
        return None


def success_response(message, data=None):
    payload = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def error_response(message, errors=None):
    payload = {"status": "error", "message": message}
    if errors is not None:
        payload["errors"] = errors
    return payload
