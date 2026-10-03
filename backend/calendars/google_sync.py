"""Copies a user's Lineup events into a dedicated "Lineup" calendar in their Google account.

Each sync makes Google match Lineup exactly: every current event is written
(created or replaced) and anything Lineup no longer has is deleted. Event ids are
derived from Lineup's own ids, so running it twice changes nothing.
"""

import base64
import hashlib
import logging
import threading
import time

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from courses.services import campus_tz

from . import google_api
from .events import collect_events
from .models import GoogleCalendarConnection

logger = logging.getLogger(__name__)

SYNC_DELAY = 2  # seconds to wait, so a burst of changes becomes one sync


def google_event_id(uid):
    """Stable Google event id from our uid. Google only allows base32hex (0-9, a-v)."""
    digest = hashlib.sha1(uid.encode()).digest()
    return base64.b32hexencode(digest).decode().lower().rstrip('=')


def to_google_event(item):
    tz = str(campus_tz())
    event = {
        'id': google_event_id(item.uid),
        'summary': item.summary,
        'location': item.location,
        'description': item.description,
        'start': {'dateTime': item.start.isoformat(), 'timeZone': tz},
        'end': {'dateTime': item.end.isoformat(), 'timeZone': tz},
        'status': 'confirmed',  # revives an event the user deleted by hand in Google
    }
    if item.recurrence:
        rule = item.recurrence
        event['recurrence'] = [
            f'RRULE:FREQ=WEEKLY;BYDAY={",".join(rule.byday)};UNTIL={rule.until:%Y%m%dT%H%M%SZ}',
        ]
        if rule.skipped:
            days = ','.join(f'{day:%Y%m%dT%H%M%S}' for day in rule.skipped)
            event['recurrence'].append(f'EXDATE;TZID={tz}:{days}')
    return event


def sync_user(user):
    conn = GoogleCalendarConnection.objects.get(user=user)
    if not conn.refresh_token:
        raise google_api.AccessRevoked('Stored Google access could not be read. Reconnect Google Calendar.')
    client = google_api.CalendarClient(google_api.access_token_for(conn.refresh_token))
    tz = str(campus_tz())

    if not conn.calendar_id:
        conn.calendar_id = client.create_calendar('Lineup', tz)
    try:
        existing = client.list_event_ids(conn.calendar_id)
    except google_api.NotFound:
        # The user deleted the Lineup calendar in Google: make a new one.
        conn.calendar_id = client.create_calendar('Lineup', tz)
        existing = set()

    desired = {event['id']: event for event in map(to_google_event, collect_events(user))}
    for event in desired.values():
        client.put_event(conn.calendar_id, event)
    for stale_id in existing - desired.keys():
        client.delete_event(conn.calendar_id, stale_id)

    conn.last_synced_at = timezone.now()
    conn.last_error = ''
    conn.save()
    return len(desired)


def sync_user_safely(user_id):
    """For background use: record failures on the connection instead of raising."""
    conn = GoogleCalendarConnection.objects.select_related('user').filter(user_id=user_id).first()
    if conn is None:
        return
    try:
        sync_user(conn.user)
    except (google_api.GoogleAPIError, requests.RequestException) as exc:
        logger.warning('Google Calendar sync failed for user %s: %s', user_id, exc)
        GoogleCalendarConnection.objects.filter(pk=conn.pk).update(last_error=str(exc))


# --- background scheduling --------------------------------------------------

_lock = threading.Lock()
_latest_request = {}  # user_id -> number of the newest sync request


def request_sync(user_ids):
    """Sync these users' Google calendars once the current transaction commits.

    on_commit: never sync data that might still be rolled back. The work then runs on a
    background thread so the student's request doesn't wait on Google's API. (A task
    queue such as Celery is the sturdier production choice; a thread keeps this simple.)
    """
    connected = list(
        GoogleCalendarConnection.objects.filter(user_id__in=set(user_ids)).values_list('user_id', flat=True)
    )
    for user_id in connected:
        transaction.on_commit(lambda user_id=user_id: _schedule(user_id))


def _schedule(user_id):
    if not settings.GOOGLE_SYNC_IN_BACKGROUND:
        sync_user_safely(user_id)
        return
    with _lock:
        ticket = _latest_request[user_id] = _latest_request.get(user_id, 0) + 1

    def run():
        time.sleep(SYNC_DELAY)
        with _lock:
            if _latest_request.get(user_id) != ticket:
                return  # a newer change arrived; its sync will include this one
        try:
            sync_user_safely(user_id)
        finally:
            connection.close()  # threads get their own DB connection; don't leak it

    threading.Thread(target=run, daemon=True).start()
