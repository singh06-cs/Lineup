from urllib.parse import quote, urlencode

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import google_api
from .builder import build_calendar
from .google_sync import sync_user
from .models import CalendarFeed, GoogleCalendarConnection

STATE_SALT = 'google-calendar-oauth'
STATE_MAX_AGE = 10 * 60  # the approval round-trip must finish within 10 minutes


class FeedLinksView(APIView):
    """GET your feed links; POST to regenerate (revokes the old URL)."""

    def get(self, request):
        feed, _ = CalendarFeed.objects.get_or_create(user=request.user)
        return Response(self.links(request, feed))

    def post(self, request):
        feed, _ = CalendarFeed.objects.get_or_create(user=request.user)
        feed.regenerate()
        return Response(self.links(request, feed))

    def links(self, request, feed):
        url = request.build_absolute_uri(reverse('calendar-ics', args=[feed.token]))
        # webcal:// tells the OS "subscribe to this", rather than download it once.
        webcal = 'webcal://' + url.split('://', 1)[1]
        return {
            'feed_url': url,
            'webcal_url': webcal,
            'google_url': f'https://calendar.google.com/calendar/r?cid={quote(webcal, safe="")}',
        }


def ics_feed(request, token):
    """The feed itself: a plain Django view, no DRF auth. The token in the URL is the
    credential, because calendar servers fetching it can't log in."""
    feed = get_object_or_404(CalendarFeed.objects.select_related('user'), token=token)
    response = HttpResponse(build_calendar(feed.user), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'inline; filename="lineup.ics"'
    # Don't let shared caches (proxies) store someone's personal schedule.
    response['Cache-Control'] = 'private, max-age=300'
    return response


def google_status(user):
    conn = GoogleCalendarConnection.objects.filter(user=user).first()
    return {
        'configured': bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        'connected': conn is not None,
        'google_email': conn.google_email if conn else None,
        'last_synced_at': conn.last_synced_at if conn else None,
        'last_error': conn.last_error if conn else '',
    }


def require_google_configured():
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        raise serializers.ValidationError({'detail': 'Google Calendar sync is not set up on this server.'})


class GoogleCalendarView(APIView):
    """GET connection status; DELETE disconnects (and revokes Lineup's Google access)."""

    def get(self, request):
        return Response(google_status(request.user))

    def delete(self, request):
        conn = GoogleCalendarConnection.objects.filter(user=request.user).first()
        if conn:
            if conn.refresh_token:
                google_api.revoke(conn.refresh_token)
            conn.delete()
        return Response(google_status(request.user))


class GoogleCalendarConnectView(APIView):
    """Returns the Google approval URL; the frontend sends the browser there."""

    def post(self, request):
        require_google_configured()
        # `state` comes back to us on the callback. Signing it (with an expiry) proves the
        # callback continues a flow WE started for THIS user, which blocks CSRF-style
        # attacks that would attach someone else's Google account to your Lineup account.
        state = signing.dumps({'user': request.user.pk}, salt=STATE_SALT)
        return Response({'authorization_url': google_api.authorization_url(state)})


class GoogleCalendarSyncView(APIView):
    """Sync now (the student is waiting, so this one runs in the request)."""

    def post(self, request):
        if not GoogleCalendarConnection.objects.filter(user=request.user).exists():
            raise serializers.ValidationError({'detail': 'Connect Google Calendar first.'})
        try:
            sync_user(request.user)
        except (google_api.GoogleAPIError, requests.RequestException) as exc:
            GoogleCalendarConnection.objects.filter(user=request.user).update(last_error=str(exc))
            return Response(
                {**google_status(request.user), 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(google_status(request.user))


def back_to_app(result, **extra):
    query = urlencode({'google': result, **extra})
    return HttpResponseRedirect(f'{settings.FRONTEND_URL}/schedule?{query}')


def google_calendar_callback(request):
    """Google redirects the BROWSER here after the approval screen (so no JWT is sent:
    the signed `state` identifies the user instead)."""
    if request.GET.get('error'):
        return back_to_app('cancelled')  # e.g. the user clicked "Cancel" on Google's screen
    try:
        data = signing.loads(request.GET.get('state', ''), salt=STATE_SALT, max_age=STATE_MAX_AGE)
        user = get_user_model().objects.get(pk=data['user'])
    except (signing.BadSignature, get_user_model().DoesNotExist, KeyError):
        return back_to_app('error', reason='expired')

    try:
        tokens = google_api.exchange_code(request.GET.get('code', ''))
    except (google_api.GoogleAPIError, requests.RequestException, ValueError):
        return back_to_app('error', reason='google')
    if settings.GOOGLE_CALENDAR_SCOPE not in tokens['scopes'] or not tokens['refresh_token']:
        # Google lets users untick permissions on the consent screen.
        return back_to_app('error', reason='permission')

    conn, _ = GoogleCalendarConnection.objects.get_or_create(
        user=user, defaults={'encrypted_refresh_token': ''},
    )
    conn.refresh_token = tokens['refresh_token']
    conn.google_email = tokens['email']
    conn.last_error = ''
    conn.save()

    try:
        sync_user(user)
    except (google_api.GoogleAPIError, requests.RequestException) as exc:
        GoogleCalendarConnection.objects.filter(pk=conn.pk).update(last_error=str(exc))
        return back_to_app('connected', synced='false')
    return back_to_app('connected')
