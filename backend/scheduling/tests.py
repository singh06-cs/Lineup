from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization

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
