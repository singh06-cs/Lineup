import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization

from . import services
from .models import Shift, Signup

User = get_user_model()

SHIFTS = '/api/shifts/'


def shift_url(shift, suffix=''):
    return f'{SHIFTS}{shift.pk}/{suffix}'


def at(hours):
    """A time `hours` from now (negative = in the past)."""
    return timezone.now() + timedelta(hours=hours)


class ShiftTestCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin1', 'admin1@example.com', 'pw-for-tests-1')
        self.member = User.objects.create_user('member1', 'member1@example.com', 'pw-for-tests-1')
        self.outsider = User.objects.create_user('outsider', 'outsider@example.com', 'pw-for-tests-1')
        self.org = Organization.objects.create(name='Chess Club')
        Membership.objects.create(user=self.admin, organization=self.org, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.member, organization=self.org)
        self.shift = self.make_shift('Tabling', start=24, end=26, capacity=2)

    def make_shift(self, title, start, end, capacity=5, org=None):
        return Shift.objects.create(
            organization=org or self.org, title=title,
            start_time=at(start), end_time=at(end), capacity=capacity,
        )

    def shift_payload(self, **overrides):
        payload = {
            'organization': self.org.pk, 'title': 'Bake sale', 'location': 'Quad',
            'start_time': at(48).isoformat(), 'end_time': at(50).isoformat(), 'capacity': 3,
        }
        payload.update(overrides)
        return payload


# ---------- Phase 8: shifts CRUD, permissions, filtering, query count ----------

class ShiftPermissionTests(ShiftTestCase):
    def test_admin_creates_shift_and_is_recorded_as_creator(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(SHIFTS, self.shift_payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created_by'], 'admin1')
        self.assertEqual(response.data['spots_left'], 3)
        self.assertTrue(response.data['can_manage'])

    def test_member_cannot_create_shift(self):
        self.client.force_authenticate(self.member)

        response = self.client.post(SHIFTS, self.shift_payload())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('organization', response.data)

    def test_outsider_cannot_create_shift_in_someone_elses_org(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.post(SHIFTS, self.shift_payload())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_edit_or_delete(self):
        self.client.force_authenticate(self.member)

        self.assertEqual(
            self.client.patch(shift_url(self.shift), {'title': 'x'}).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(shift_url(self.shift)).status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_see_shift(self):
        self.client.force_authenticate(self.outsider)

        self.assertEqual(self.client.get(shift_url(self.shift)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(SHIFTS).data['count'], 0)

    def test_admin_edits_shift(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(shift_url(self.shift), {'title': 'Tabling (Quad)'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Tabling (Quad)')

    def test_cannot_move_shift_to_another_org(self):
        other = Organization.objects.create(name='Robotics')
        Membership.objects.create(user=self.admin, organization=other, role=Membership.Role.ADMIN)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(shift_url(self.shift), {'organization': other.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ShiftValidationTests(ShiftTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_end_must_be_after_start(self):
        response = self.client.post(SHIFTS, self.shift_payload(end_time=at(47).isoformat()))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_time', response.data)

    def test_patch_end_before_existing_start_is_rejected(self):
        response = self.client.patch(shift_url(self.shift), {'end_time': at(23).isoformat()})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_capacity_must_be_at_least_one(self):
        response = self.client.post(SHIFTS, self.shift_payload(capacity=0))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('capacity', response.data)

    def test_capacity_cannot_drop_below_current_signups(self):
        Signup.objects.create(user=self.admin, shift=self.shift)
        Signup.objects.create(user=self.member, shift=self.shift)

        response = self.client.patch(shift_url(self.shift), {'capacity': 1})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ShiftListTests(ShiftTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.member)

    def titles(self, params=''):
        return [s['title'] for s in self.client.get(f'{SHIFTS}{params}').data['results']]

    def test_list_is_paginated_and_ordered_by_start_time(self):
        self.make_shift('Earlier', start=2, end=3)

        response = self.client.get(SHIFTS)

        self.assertEqual(response.data['count'], 2)
        self.assertEqual([s['title'] for s in response.data['results']], ['Earlier', 'Tabling'])

    def test_upcoming_filter(self):
        self.make_shift('Past', start=-5, end=-4)

        self.assertEqual(self.titles('?upcoming=true'), ['Tabling'])
        self.assertEqual(self.titles('?upcoming=false'), ['Past'])

    def test_available_and_mine_filters(self):
        full = self.make_shift('Full', start=30, end=31, capacity=1)
        Signup.objects.create(user=self.admin, shift=full)
        Signup.objects.create(user=self.member, shift=self.shift)

        self.assertEqual(self.titles('?available=true'), ['Tabling'])
        self.assertEqual(self.titles('?mine=true'), ['Tabling'])

    def test_date_range_and_org_filters(self):
        other = Organization.objects.create(name='Robotics')
        Membership.objects.create(user=self.member, organization=other)
        self.make_shift('Robot demo', start=100, end=101, org=other)

        self.assertEqual(self.titles(f'?organization={other.pk}'), ['Robot demo'])
        params = f'?starts_after={at(99).isoformat()}'.replace('+', '%2B')
        self.assertEqual(self.titles(params), ['Robot demo'])

    def test_search(self):
        self.make_shift('Bake sale', start=5, end=6)

        self.assertEqual(self.titles('?search=bake'), ['Bake sale'])

    def test_computed_fields(self):
        Signup.objects.create(user=self.member, shift=self.shift)

        data = self.client.get(shift_url(self.shift)).data

        self.assertEqual(data['signup_count'], 1)
        self.assertEqual(data['spots_left'], 1)
        self.assertTrue(data['is_signed_up'])
        self.assertFalse(data['can_manage'])

    def test_query_count_does_not_grow_with_rows(self):
        # N+1 guard: 1 COUNT query for pagination + 1 query for the page, regardless of size.
        for i in range(15):
            shift = self.make_shift(f'Shift {i}', start=30 + i * 3, end=31 + i * 3)
            Signup.objects.create(user=self.admin, shift=shift)

        with self.assertNumQueries(2):
            response = self.client.get(SHIFTS)

        self.assertEqual(response.data['count'], 16)


# ---------- Phase 9: signups ----------

class SignupTests(ShiftTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.member)

    def signup(self, shift):
        return self.client.post(shift_url(shift, 'signup/'))

    def test_sign_up_and_cancel(self):
        joined = self.signup(self.shift)
        self.assertEqual(joined.status_code, status.HTTP_201_CREATED)
        self.assertTrue(joined.data['is_signed_up'])
        self.assertEqual(joined.data['spots_left'], 1)

        cancelled = self.client.delete(shift_url(self.shift, 'signup/'))
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertFalse(cancelled.data['is_signed_up'])
        self.assertEqual(cancelled.data['spots_left'], 2)

    def test_cannot_sign_up_twice(self):
        self.signup(self.shift)

        response = self.signup(self.shift)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Signup.objects.filter(shift=self.shift).count(), 1)

    def test_cannot_sign_up_for_full_shift(self):
        Signup.objects.create(user=self.admin, shift=self.shift)
        Signup.objects.create(user=self.outsider, shift=self.shift)

        response = self.signup(self.shift)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('full', str(response.data['detail']))

    def test_cannot_sign_up_for_overlapping_shift(self):
        self.signup(self.shift)  # 24h -> 26h
        overlapping = self.make_shift('Cleanup', start=25, end=27)

        response = self.signup(overlapping)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Tabling', str(response.data['detail']))

    def test_back_to_back_shifts_do_not_overlap(self):
        self.signup(self.shift)  # ends at 26h
        next_one = self.make_shift('Next', start=26, end=28)

        self.assertEqual(self.signup(next_one).status_code, status.HTTP_201_CREATED)

    def test_overlap_is_checked_across_organizations(self):
        other = Organization.objects.create(name='Robotics')
        Membership.objects.create(user=self.member, organization=other)
        self.signup(self.shift)

        response = self.signup(self.make_shift('Robot demo', start=25, end=26, org=other))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_sign_up_or_cancel_after_shift_started(self):
        started = self.make_shift('Now', start=-1, end=1)
        Signup.objects.create(user=self.admin, shift=started)

        self.assertEqual(self.signup(started).status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.delete(shift_url(started, 'signup/')).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_cancel_when_not_signed_up(self):
        response = self.client.delete(shift_url(self.shift, 'signup/'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_outsider_cannot_sign_up(self):
        self.client.force_authenticate(self.outsider)

        self.assertEqual(self.signup(self.shift).status_code, status.HTTP_404_NOT_FOUND)

    def test_roster_is_admin_only(self):
        self.signup(self.shift)

        self.assertEqual(
            self.client.get(shift_url(self.shift, 'roster/')).status_code, status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.admin)
        roster = self.client.get(shift_url(self.shift, 'roster/'))
        self.assertEqual([r['user']['username'] for r in roster.data], ['member1'])


class ConcurrentSignupTests(TransactionTestCase):
    """The showcase test: many people grab the last spots at the same instant.

    TransactionTestCase (not TestCase) because each thread needs its own real
    database connection and transaction; TestCase wraps everything in one.
    """

    def test_shift_is_never_overbooked(self):
        org = Organization.objects.create(name='Chess Club')
        shift = Shift.objects.create(
            organization=org, title='Last spots', start_time=at(24), end_time=at(26), capacity=2,
        )
        users = [
            User.objects.create_user(f'racer{i}', f'racer{i}@example.com', 'pw-for-tests-1')
            for i in range(8)
        ]
        start_together = threading.Barrier(len(users))
        results = []

        def attempt(user):
            start_together.wait()  # release all threads at the same moment
            try:
                services.sign_up(user, shift)
                results.append('ok')
            except ValidationError:
                results.append('rejected')
            finally:
                connection.close()  # each thread opened its own connection

        threads = [threading.Thread(target=attempt, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count('ok'), 2)
        self.assertEqual(results.count('rejected'), 6)
        self.assertEqual(Signup.objects.filter(shift=shift).count(), 2)


# ---------- Phase 15: shift signups respect class schedules ----------

class ShiftClassConflictTests(ShiftTestCase):
    def setUp(self):
        from datetime import date, time

        from courses.models import Course, Enrollment, Meeting, Section, Term

        super().setUp()
        today = timezone.localdate()
        term = Term.objects.create(
            name='Test term', instruction_begins=today, instruction_ends=today + timedelta(days=60),
        )
        section = Section.objects.create(
            term=term, crn='12345',
            course=Course.objects.create(subject='ECS', number='036A', title='Python'),
        )
        # A class that meets every day, all day: any shift in the term will clash.
        Meeting.objects.create(section=section, days='MTWRFSU', start_time=time(0), end_time=time(23, 59))
        Enrollment.objects.create(user=self.member, section=section)
        self.client.force_authenticate(self.member)
        self.date = date

    def test_cannot_sign_up_for_shift_during_class(self):
        response = self.client.post(shift_url(self.shift, 'signup/'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('overlaps your class', str(response.data['detail']))

    def test_conflicts_endpoint_lists_existing_signups_that_now_clash(self):
        # Signed up before enrolling (created directly, bypassing the rule).
        Signup.objects.create(user=self.member, shift=self.shift)

        response = self.client.get(f'{SHIFTS}class-conflicts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['shift']['title'], 'Tabling')
        self.assertIn('ECS 036A', response.data[0]['conflicts'][0])


# ---------- Phase 16: club meetings ----------

class ClubMeetingTests(ShiftTestCase):
    URL = '/api/club-meetings/'

    def setUp(self):
        from courses.models import Term

        super().setUp()
        self.term = Term.objects.create(
            name='Fall 2026', instruction_begins=at(-24).date(), instruction_ends=at(24 * 60).date(),
        )

    def payload(self, **overrides):
        data = {
            'organization': self.org.pk, 'term': self.term.pk, 'title': 'General meeting',
            'days': 't', 'start_time': '18:00', 'end_time': '19:00', 'location': 'Wellman 26',
        }
        data.update(overrides)
        return data

    def test_admin_schedules_weekly_meeting(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.URL, self.payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['days'], 'T')
        self.assertTrue(response.data['can_manage'])

    def test_member_sees_but_cannot_create_or_edit(self):
        self.client.force_authenticate(self.admin)
        meeting_id = self.client.post(self.URL, self.payload()).data['id']
        self.client.force_authenticate(self.member)

        listed = self.client.get(f'{self.URL}?organization={self.org.pk}')
        created = self.client.post(self.URL, self.payload())
        edited = self.client.patch(f'{self.URL}{meeting_id}/', {'title': 'x'})

        self.assertEqual([m['id'] for m in listed.data], [meeting_id])
        self.assertEqual(created.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(edited.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_sees_nothing(self):
        self.client.force_authenticate(self.admin)
        self.client.post(self.URL, self.payload())
        self.client.force_authenticate(self.outsider)

        self.assertEqual(self.client.get(self.URL).data, [])

    def test_end_after_start(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.URL, self.payload(end_time='17:00'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
