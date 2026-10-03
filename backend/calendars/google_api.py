"""The only module that talks to Google over HTTP: OAuth tokens and the Calendar API.

Keeping every network call here means the rest of the code is plain Python, and
tests can replace this one module with a fake instead of hitting Google.
"""

from urllib.parse import quote, urlencode

import requests
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
CALENDAR_API = 'https://www.googleapis.com/calendar/v3'
TIMEOUT = 15  # seconds; never let a slow Google response hang a worker forever


class GoogleAPIError(Exception):
    pass


class NotFound(GoogleAPIError):
    """404/410: e.g. the user deleted the Lineup calendar in Google."""


class AccessRevoked(GoogleAPIError):
    """The user removed Lineup's access in their Google account settings."""


def authorization_url(state):
    """Where to send the browser so the user can approve calendar access."""
    return AUTH_URL + '?' + urlencode({
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        # openid + email only identify which Google account was connected.
        'scope': f'openid email {settings.GOOGLE_CALENDAR_SCOPE}',
        'access_type': 'offline',  # ask for a refresh token, to sync later without the user present
        'prompt': 'consent',       # always return a refresh token, even on reconnect
        'include_granted_scopes': 'true',
        'state': state,
    })


def exchange_code(code):
    """Trade the one-time code from the redirect for tokens (server-to-server, with our secret)."""
    response = requests.post(TOKEN_URL, data={
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }, timeout=TIMEOUT)
    if response.status_code != 200:
        raise GoogleAPIError(f'Token exchange failed ({response.status_code}).')
    tokens = response.json()
    info = id_token.verify_oauth2_token(tokens['id_token'], google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    return {
        'refresh_token': tokens.get('refresh_token'),
        'scopes': tokens.get('scope', '').split(),
        'email': info.get('email', ''),
    }


def access_token_for(refresh_token):
    """Access tokens last about an hour, so each sync trades the refresh token for a fresh one."""
    response = requests.post(TOKEN_URL, data={
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, timeout=TIMEOUT)
    if response.status_code == 400 and response.json().get('error') == 'invalid_grant':
        raise AccessRevoked('Google access was removed. Reconnect Google Calendar to keep syncing.')
    if response.status_code != 200:
        raise GoogleAPIError(f'Could not refresh Google access ({response.status_code}).')
    return response.json()['access_token']


def revoke(token):
    # Best effort: disconnecting in Lineup should still work if Google is unreachable.
    try:
        requests.post(REVOKE_URL, data={'token': token}, timeout=TIMEOUT)
    except requests.RequestException:
        pass


class CalendarClient:
    def __init__(self, access_token):
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {access_token}'

    def _request(self, method, path, **kwargs):
        response = self.session.request(method, CALENDAR_API + path, timeout=TIMEOUT, **kwargs)
        if response.status_code in (404, 410):
            raise NotFound(path)
        if response.status_code >= 400:
            raise GoogleAPIError(f'Google Calendar {method} failed ({response.status_code}).')
        return response.json() if response.content else {}

    def create_calendar(self, summary, time_zone):
        return self._request('POST', '/calendars', json={'summary': summary, 'timeZone': time_zone})['id']

    def list_event_ids(self, calendar_id):
        ids, page = set(), None
        while True:
            params = {'maxResults': 2500, 'fields': 'items(id),nextPageToken'}
            if page:
                params['pageToken'] = page
            data = self._request('GET', f'/calendars/{quote(calendar_id, safe="")}/events', params=params)
            ids.update(item['id'] for item in data.get('items', []))
            page = data.get('nextPageToken')
            if not page:
                return ids

    def put_event(self, calendar_id, event):
        """Create or replace, using OUR event id, so re-syncing never duplicates events."""
        base = f'/calendars/{quote(calendar_id, safe="")}/events'
        try:
            self._request('PUT', f'{base}/{event["id"]}', json=event)
        except NotFound:
            self._request('POST', base, json=event)

    def delete_event(self, calendar_id, event_id):
        try:
            self._request('DELETE', f'/calendars/{quote(calendar_id, safe="")}/events/{event_id}')
        except NotFound:
            pass
