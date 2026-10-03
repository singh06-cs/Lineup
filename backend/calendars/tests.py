from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from django.contrib.auth import get_user_model
from django.utils import timezone
from icalendar import Calendar
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course, Enrollment, Holiday, Meeting, Section, Term
from organizations.models import Membership, Organization
from scheduling.models import ClubMeeting, Shift, Signup

from .models import CalendarFeed

User = get_user_model()
PACIFIC = ZoneInfo('America/Los_Angeles')
FEED_LINKS = '/api/calendar/feed/'


class CalendarFeedTestCase(APITestCase):
    """Alice takes ECS 036A (MWF 10:00-10:50) in the real Fall 2026 term."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@example.com', 'pw-for-tests-1')
        self.bob = User.objects.create_user('bob', 'bob@example.com', 'pw-for-tests-1')
        self.term = Term.objects.create(
            name='Fall 2026', instruction_begins=date(2026, 9, 23), instruction_ends=date(2026, 12, 4),
        )
        for day, name in [(date(2026, 11, 11), 'Veterans Day'), (date(2026, 11, 26), 'Thanksgiving'),
                          (date(2026, 11, 27), 'Thanksgiving')]:
            Holiday.objects.create(term=self.term, date=day, name=name)
        self.section = Section.objects.create(
            term=self.term, crn='12345', instructor='Lee',
            course=Course.objects.create(subject='ECS', number='036A', title='Programming in Python'),
        )
        self.lecture = Meeting.objects.create(
            section=self.section, days='MWF', start_time=time(10), end_time=time(10, 50),
            location='Wellman 2',
        )
        Enrollment.objects.create(user=self.alice, section=self.section)

    def feed_for(self, user):
        self.client.force_authenticate(user)
        url = self.client.get(FEED_LINKS).data['feed_url']
        self.client.force_authenticate(None)  # the feed itself needs no login
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response, Calendar.from_ical(response.content)

    def events(self, cal):
        return {str(e['UID']): e for e in cal.walk('VEVENT')}

    def occurrences(self, event):
        """Expand RRULE minus EXDATE into concrete start times, like a calendar app would."""
        start = event['DTSTART'].dt
        rule = rrulestr(event['RRULE'].to_ical().decode(), dtstart=start)
        exdates = event.get('EXDATE')
        skipped = {d.dt for d in (exdates.dts if exdates else [])}
        return [occurrence for occurrence in rule if occurrence not in skipped]


class FeedLinkTests(CalendarFeedTestCase):
    def test_links_require_login(self):
        self.assertEqual(self.client.get(FEED_LINKS).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_links(self):
        self.client.force_authenticate(self.alice)

        data = self.client.get(FEED_LINKS).data

        token = CalendarFeed.objects.get(user=self.alice).token
        self.assertTrue(data['feed_url'].endswith(f'/calendar/{token}.ics'))
        self.assertTrue(data['webcal_url'].startswith('webcal://'))
        self.assertTrue(data['google_url'].startswith('https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F'))

    def test_regenerate_revokes_old_url(self):
        self.client.force_authenticate(self.alice)
        old_url = self.client.get(FEED_LINKS).data['feed_url']

        new_url = self.client.post(FEED_LINKS).data['feed_url']

        self.assertNotEqual(old_url, new_url)
        self.assertEqual(self.client.get(old_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(new_url).status_code, status.HTTP_200_OK)

    def test_unknown_token_is_404(self):
        self.assertEqual(self.client.get('/calendar/not-a-real-token.ics').status_code, status.HTTP_404_NOT_FOUND)


class FeedContentTests(CalendarFeedTestCase):
    def test_response_is_a_private_calendar(self):
        response, cal = self.feed_for(self.alice)

        self.assertTrue(response['Content-Type'].startswith('text/calendar'))
        self.assertIn('private', response['Cache-Control'])
        self.assertTrue(cal.walk('VTIMEZONE'), 'needs a VTIMEZONE for America/Los_Angeles')

    def test_class_is_one_recurring_event(self):
        _, cal = self.feed_for(self.alice)
        lecture = self.events(cal)[f'meeting-{self.lecture.pk}@lineup']

        self.assertEqual(str(lecture['SUMMARY']), 'ECS 036A Lecture')
        self.assertEqual(lecture['RRULE']['FREQ'], ['WEEKLY'])
        self.assertEqual(lecture['RRULE']['BYDAY'], ['MO', 'WE', 'FR'])
        # Instruction begins Wed Sep 23, so that's the first class.
        self.assertEqual(lecture['DTSTART'].dt, datetime(2026, 9, 23, 10, 0, tzinfo=PACIFIC))

    def test_occurrences_match_the_real_quarter(self):
        """Expand the rule and compare with an independent day-by-day count."""
        _, cal = self.feed_for(self.alice)
        lecture = self.events(cal)[f'meeting-{self.lecture.pk}@lineup']

        holidays = {date(2026, 11, 11), date(2026, 11, 26), date(2026, 11, 27)}
        expected = []
        day = date(2026, 9, 23)
        while day <= date(2026, 12, 4):
            if day.weekday() in (0, 2, 4) and day not in holidays:
                expected.append(datetime(day.year, day.month, day.day, 10, 0, tzinfo=PACIFIC))
            day += timedelta(days=1)

        occurrences = self.occurrences(lecture)
        self.assertEqual(occurrences, expected)
        self.assertEqual(len(occurrences), 30)
        # Veterans Day (Wed) and Thanksgiving Friday are skipped...
        self.assertNotIn(datetime(2026, 11, 11, 10, tzinfo=PACIFIC), occurrences)
        self.assertNotIn(datetime(2026, 11, 27, 10, tzinfo=PACIFIC), occurrences)
        # ...and after daylight saving ends (Nov 1) class is still 10:00 local = 18:00 UTC.
        self.assertIn(datetime(2026, 11, 2, 18, 0, tzinfo=timezone.UTC), occurrences)

    def test_finals_club_meetings_and_shifts_included(self):
        final_start = datetime(2026, 12, 8, 8, 0, tzinfo=PACIFIC)
        self.section.final_exam_start = final_start
        self.section.final_exam_end = final_start + timedelta(hours=2)
        self.section.save()
        org = Organization.objects.create(name='Chess Club')
        Membership.objects.create(user=self.alice, organization=org)
        club = ClubMeeting.objects.create(
            organization=org, term=self.term, days='T', start_time=time(18), end_time=time(19),
        )
        shift = Shift.objects.create(
            organization=org, title='Tabling', capacity=2,
            start_time=datetime(2026, 10, 3, 17, tzinfo=timezone.UTC),
            end_time=datetime(2026, 10, 3, 19, tzinfo=timezone.UTC),
        )
        Signup.objects.create(user=self.alice, shift=shift)
        Shift.objects.create(  # a shift alice did NOT sign up for
            organization=org, title='Not mine', capacity=2,
            start_time=datetime(2026, 10, 4, 17, tzinfo=timezone.UTC),
            end_time=datetime(2026, 10, 4, 19, tzinfo=timezone.UTC),
        )

        _, cal = self.feed_for(self.alice)
        events = self.events(cal)

        self.assertEqual(str(events[f'final-{self.section.pk}@lineup']['SUMMARY']), 'ECS 036A Final Exam')
        self.assertEqual(str(events[f'club-meeting-{club.pk}@lineup']['SUMMARY']), 'Chess Club: General meeting')
        self.assertEqual(str(events[f'shift-{shift.pk}@lineup']['SUMMARY']), 'Chess Club: Tabling')
        self.assertEqual(len(events), 4)  # lecture, final, club meeting, signed-up shift only

    def test_feed_only_contains_its_owners_data(self):
        _, cal = self.feed_for(self.bob)

        self.assertEqual(self.events(cal), {})


# ---------- Phase 19: direct Google Calendar sync (Google is faked) ----------

from unittest.mock import patch  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

from django.core import signing  # noqa: E402
from django.test import override_settings  # noqa: E402

from . import google_api  # noqa: E402
from .events import collect_events  # noqa: E402
from .google_sync import google_event_id, sync_user, to_google_event  # noqa: E402
from .models import GoogleCalendarConnection  # noqa: E402
from .views import STATE_SALT  # noqa: E402

GOOGLE_SETTINGS = {
    'GOOGLE_CLIENT_ID': 'test-client-id',
    'GOOGLE_CLIENT_SECRET': 'test-secret',
    'GOOGLE_SYNC_IN_BACKGROUND': False,
    'FRONTEND_URL': 'http://app.test',
}


class FakeGoogleCalendar:
    """Stands in for google_api.CalendarClient: stores calendars and events in memory."""

    calendars = {}

    def __init__(self, access_token):
        assert access_token == 'fresh-access-token'

    def create_calendar(self, summary, time_zone):
        calendar_id = f'lineup{len(self.calendars) + 1}@group.calendar.google.com'
        self.calendars[calendar_id] = {}
        return calendar_id

    def list_event_ids(self, calendar_id):
        if calendar_id not in self.calendars:
            raise google_api.NotFound(calendar_id)
        return set(self.calendars[calendar_id])

    def put_event(self, calendar_id, event):
        self.calendars[calendar_id][event['id']] = event

    def delete_event(self, calendar_id, event_id):
        self.calendars[calendar_id].pop(event_id, None)


@override_settings(**GOOGLE_SETTINGS)
class GoogleSyncTestCase(CalendarFeedTestCase):
    def setUp(self):
        super().setUp()
        FakeGoogleCalendar.calendars = {}
        patches = [
            patch('calendars.google_api.CalendarClient', FakeGoogleCalendar),
            patch('calendars.google_api.access_token_for', return_value='fresh-access-token'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def connect(self, user):
        conn = GoogleCalendarConnection(user=user, google_email='alice@gmail.com')
        conn.refresh_token = 'refresh-token-secret'
        conn.save()
        return conn

    def google_events(self, user):
        conn = GoogleCalendarConnection.objects.get(user=user)
        return FakeGoogleCalendar.calendars.get(conn.calendar_id, {})


class GoogleEventFormatTests(GoogleSyncTestCase):
    def test_class_becomes_one_recurring_google_event(self):
        lecture = next(e for e in collect_events(self.alice) if e.uid.startswith('meeting-'))

        event = to_google_event(lecture)

        self.assertEqual(event['start'], {'dateTime': '2026-09-23T10:00:00-07:00', 'timeZone': 'America/Los_Angeles'})
        self.assertEqual(event['recurrence'], [
            'RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261205T075959Z',
            'EXDATE;TZID=America/Los_Angeles:20261111T100000,20261127T100000',
        ])

    def test_event_ids_are_stable_and_google_compatible(self):
        first, again = google_event_id('meeting-1@lineup'), google_event_id('meeting-1@lineup')

        self.assertEqual(first, again)
        self.assertNotEqual(first, google_event_id('meeting-2@lineup'))
        self.assertRegex(first, r'^[0-9a-v]{5,1024}$')  # Google's allowed id characters


class GoogleSyncTests(GoogleSyncTestCase):
    def test_refresh_token_is_encrypted_at_rest(self):
        conn = self.connect(self.alice)

        stored = GoogleCalendarConnection.objects.values_list('encrypted_refresh_token', flat=True).get(pk=conn.pk)
        self.assertNotIn('refresh-token-secret', stored)
        self.assertEqual(GoogleCalendarConnection.objects.get(pk=conn.pk).refresh_token, 'refresh-token-secret')

    def test_sync_creates_a_lineup_calendar_with_the_users_events(self):
        self.connect(self.alice)

        count = sync_user(self.alice)

        self.assertEqual(count, 1)
        self.assertEqual([e['summary'] for e in self.google_events(self.alice).values()], ['ECS 036A Lecture'])
        self.assertIsNotNone(GoogleCalendarConnection.objects.get(user=self.alice).last_synced_at)

    def test_resync_does_not_duplicate_and_removes_dropped_classes(self):
        self.connect(self.alice)
        sync_user(self.alice)
        sync_user(self.alice)
        self.assertEqual(len(self.google_events(self.alice)), 1)

        Enrollment.objects.filter(user=self.alice).delete()
        sync_user(self.alice)

        self.assertEqual(self.google_events(self.alice), {})

    def test_calendar_deleted_in_google_is_recreated(self):
        self.connect(self.alice)
        sync_user(self.alice)
        FakeGoogleCalendar.calendars.clear()  # the user deleted "Lineup" in Google

        sync_user(self.alice)

        self.assertEqual(len(self.google_events(self.alice)), 1)

    def test_changes_sync_automatically_after_commit(self):
        self.connect(self.alice)
        sync_user(self.alice)
        org = Organization.objects.create(name='Chess Club')

        with self.captureOnCommitCallbacks(execute=True):
            Membership.objects.create(user=self.alice, organization=org)
        with self.captureOnCommitCallbacks(execute=True):
            ClubMeeting.objects.create(organization=org, term=self.term, days='T', start_time=time(18), end_time=time(19))

        summaries = sorted(e['summary'] for e in self.google_events(self.alice).values())
        self.assertEqual(summaries, ['Chess Club: General meeting', 'ECS 036A Lecture'])

    def test_users_without_a_connection_are_never_synced(self):
        with patch('calendars.google_sync.sync_user_safely') as sync:
            with self.captureOnCommitCallbacks(execute=True):
                Enrollment.objects.create(
                    user=self.bob, section=self.section,
                )
        sync.assert_not_called()

    def test_revoked_access_is_reported_not_crashed(self):
        self.connect(self.alice)
        self.client.force_authenticate(self.alice)

        with patch('calendars.google_api.access_token_for',
                   side_effect=google_api.AccessRevoked('Google access was removed.')):
            response = self.client.post('/api/calendar/google/sync/')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn('removed', response.data['last_error'])

    def test_disconnect_revokes_and_forgets_tokens(self):
        self.connect(self.alice)
        self.client.force_authenticate(self.alice)

        with patch('calendars.google_api.revoke') as revoke:
            response = self.client.delete('/api/calendar/google/')

        revoke.assert_called_once_with('refresh-token-secret')
        self.assertFalse(response.data['connected'])
        self.assertFalse(GoogleCalendarConnection.objects.exists())


class GoogleOAuthFlowTests(GoogleSyncTestCase):
    CALLBACK = '/api/calendar/google/callback/'

    def state_for(self, user):
        return signing.dumps({'user': user.pk}, salt=STATE_SALT)

    def test_connect_returns_google_approval_url(self):
        self.client.force_authenticate(self.alice)

        url = self.client.post('/api/calendar/google/connect/').data['authorization_url']

        params = parse_qs(urlparse(url).query)
        self.assertEqual(params['client_id'], ['test-client-id'])
        self.assertIn('https://www.googleapis.com/auth/calendar.app.created', params['scope'][0])
        self.assertEqual(params['access_type'], ['offline'])
        self.assertEqual(signing.loads(params['state'][0], salt=STATE_SALT), {'user': self.alice.pk})

    def test_connect_refused_when_google_not_configured(self):
        self.client.force_authenticate(self.alice)
        with override_settings(GOOGLE_CLIENT_ID=''):
            self.assertEqual(self.client.post('/api/calendar/google/connect/').status_code, 400)

    def test_successful_callback_stores_connection_and_syncs(self):
        tokens = {'refresh_token': 'refresh-token-secret', 'email': 'alice@gmail.com',
                  'scopes': ['openid', 'https://www.googleapis.com/auth/calendar.app.created']}
        with patch('calendars.google_api.exchange_code', return_value=tokens):
            response = self.client.get(self.CALLBACK, {'code': 'one-time-code', 'state': self.state_for(self.alice)})

        self.assertEqual(response['Location'], 'http://app.test/schedule?google=connected')
        conn = GoogleCalendarConnection.objects.get(user=self.alice)
        self.assertEqual(conn.google_email, 'alice@gmail.com')
        self.assertEqual(len(self.google_events(self.alice)), 1)

    def test_tampered_or_expired_state_rejected(self):
        response = self.client.get(self.CALLBACK, {'code': 'x', 'state': 'forged-state'})

        self.assertIn('google=error', response['Location'])
        self.assertFalse(GoogleCalendarConnection.objects.exists())

    def test_user_cancelled_on_google(self):
        response = self.client.get(self.CALLBACK, {'error': 'access_denied', 'state': self.state_for(self.alice)})

        self.assertIn('google=cancelled', response['Location'])

    def test_calendar_permission_unticked(self):
        tokens = {'refresh_token': 'r', 'email': 'a@gmail.com', 'scopes': ['openid', 'email']}
        with patch('calendars.google_api.exchange_code', return_value=tokens):
            response = self.client.get(self.CALLBACK, {'code': 'x', 'state': self.state_for(self.alice)})

        self.assertIn('reason=permission', response['Location'])
        self.assertFalse(GoogleCalendarConnection.objects.exists())



class GoogleHttpClientTests(APITestCase):
    """google_api.py at the HTTP level (requests is mocked, nothing leaves the machine)."""

    def response(self, status_code, body=None):
        class FakeResponse:
            content = b'{}' if body is not None else b''

            def json(self):
                return body or {}
        fake = FakeResponse()
        fake.status_code = status_code
        return fake

    def test_invalid_grant_means_access_was_revoked(self):
        with patch('calendars.google_api.requests.post', return_value=self.response(400, {'error': 'invalid_grant'})):
            with self.assertRaises(google_api.AccessRevoked):
                google_api.access_token_for('old-refresh-token')

    def test_put_falls_back_to_insert_for_new_events(self):
        client = google_api.CalendarClient('access')
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url.rsplit('/calendar/v3', 1)[1]))
            return self.response(404 if method == 'PUT' else 200, {'id': 'abc'})

        with patch.object(client.session, 'request', side_effect=fake_request):
            client.put_event('lineup@group.calendar.google.com', {'id': 'abc12'})

        self.assertEqual(calls, [
            ('PUT', '/calendars/lineup%40group.calendar.google.com/events/abc12'),
            ('POST', '/calendars/lineup%40group.calendar.google.com/events'),
        ])
