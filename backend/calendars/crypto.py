"""Encrypts OAuth tokens before they're stored.

A Google refresh token is a long-lived key to that user's calendar. If the database
leaked (a backup, a SQL injection), plain-text tokens would hand attackers access;
encrypted ones are useless without the key, which lives in the environment, not the DB.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = os.environ.get('TOKEN_ENCRYPTION_KEY')
    if not key:
        # Fall back to a key derived from SECRET_KEY. Simpler, but rotating SECRET_KEY then
        # makes stored tokens unreadable (users just reconnect). Production should set
        # TOKEN_ENCRYPTION_KEY (generate with Fernet.generate_key()).
        digest = hashlib.sha256(b'lineup-oauth-tokens:' + settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
