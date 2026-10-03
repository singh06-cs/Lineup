import secrets

from django.conf import settings
from django.db import models

from .crypto import decrypt, encrypt


def generate_feed_token():
    # 32 random bytes: unguessable, so the URL itself can act as the password.
    return secrets.token_urlsafe(32)


class CalendarFeed(models.Model):
    """A secret URL that serves one user's calendar.

    Calendar apps (Google, Apple, Outlook) fetch subscribed feeds from their own servers
    and can't log in or send our JWT, so the unguessable token IS the credential.
    Regenerating it revokes the old URL, the same idea as an org's invite code.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_feed',
    )
    token = models.CharField(max_length=64, unique=True, default=generate_feed_token)
    created_at = models.DateTimeField(auto_now_add=True)

    def regenerate(self):
        self.token = generate_feed_token()
        self.save(update_fields=['token'])

    def __str__(self):
        return f'Calendar feed for {self.user}'


class GoogleCalendarConnection(models.Model):
    """A user's permission for Lineup to write to a "Lineup" calendar in their Google account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar',
    )
    google_email = models.EmailField(blank=True)
    # Encrypted at rest (see crypto.py); use the refresh_token property, never this field.
    encrypted_refresh_token = models.TextField()
    # The secondary calendar Lineup created; empty until the first sync creates it.
    calendar_id = models.CharField(max_length=255, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    @property
    def refresh_token(self):
        return decrypt(self.encrypted_refresh_token)

    @refresh_token.setter
    def refresh_token(self, value):
        self.encrypted_refresh_token = encrypt(value)

    def __str__(self):
        return f'Google Calendar for {self.user}'
