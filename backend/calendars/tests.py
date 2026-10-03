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
