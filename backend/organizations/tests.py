from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Membership, Organization

User = get_user_model()

ORGS = '/api/organizations/'


def org_url(org, suffix=''):
    return f'{ORGS}{org.pk}/{suffix}'


class OrgTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset throttle counters between tests
        self.admin = User.objects.create_user('admin1', 'admin1@example.com', 'pw-for-tests-1')
        self.member = User.objects.create_user('member1', 'member1@example.com', 'pw-for-tests-1')
        self.outsider = User.objects.create_user('outsider', 'outsider@example.com', 'pw-for-tests-1')
        self.org = Organization.objects.create(name='Chess Club')
        self.admin_membership = Membership.objects.create(
            user=self.admin, organization=self.org, role=Membership.Role.ADMIN,
        )
        self.member_membership = Membership.objects.create(user=self.member, organization=self.org)


class CreateAndListTests(OrgTestCase):
    def test_creator_becomes_admin(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.post(ORGS, {'name': 'Robotics'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['my_role'], 'admin')
        self.assertEqual(response.data['member_count'], 1)
        self.assertIn('invite_code', response.data)
        org = Organization.objects.get(name='Robotics')
        self.assertTrue(org.memberships.filter(user=self.outsider, role='admin').exists())

    def test_list_only_shows_my_orgs_with_correct_counts(self):
        Organization.objects.create(name='Not mine')
        self.client.force_authenticate(self.member)

        response = self.client.get(ORGS)

        results = response.data['results']
        self.assertEqual([o['name'] for o in results], ['Chess Club'])
        self.assertEqual(results[0]['member_count'], 2)
        self.assertEqual(results[0]['my_role'], 'member')

    def test_invite_code_hidden_from_regular_members(self):
        self.client.force_authenticate(self.member)

        response = self.client.get(org_url(self.org))

        self.assertNotIn('invite_code', response.data)

    def test_outsider_gets_404_not_403(self):
        # 404 doesn't even reveal that the org exists.
        self.client.force_authenticate(self.outsider)

        self.assertEqual(self.client.get(org_url(self.org)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.get(org_url(self.org, 'members/')).status_code, status.HTTP_404_NOT_FOUND,
        )

    def test_requires_login(self):
        self.assertEqual(self.client.get(ORGS).status_code, status.HTTP_401_UNAUTHORIZED)


class AdminPermissionTests(OrgTestCase):
    def test_member_cannot_edit_or_delete(self):
        self.client.force_authenticate(self.member)

        edit = self.client.patch(org_url(self.org), {'name': 'Hacked'})
        delete = self.client.delete(org_url(self.org))

        self.assertEqual(edit.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_edit(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(org_url(self.org), {'name': 'Chess & Go Club'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Chess & Go Club')

    def test_regenerate_invite_code_invalidates_old_code(self):
        old_code = self.org.invite_code
        self.client.force_authenticate(self.admin)

        response = self.client.post(org_url(self.org, 'regenerate-invite-code/'))

        self.assertNotEqual(response.data['invite_code'], old_code)
        self.client.force_authenticate(self.outsider)
        join = self.client.post(f'{ORGS}join/', {'invite_code': old_code})
        self.assertEqual(join.status_code, status.HTTP_404_NOT_FOUND)


class JoinTests(OrgTestCase):
    def test_join_with_valid_code(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.post(f'{ORGS}join/', {'invite_code': self.org.invite_code})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['my_role'], 'member')

    def test_join_with_bad_code(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.post(f'{ORGS}join/', {'invite_code': 'nope'})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_join_twice(self):
        self.client.force_authenticate(self.member)

        response = self.client.post(f'{ORGS}join/', {'invite_code': self.org.invite_code})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_is_rate_limited(self):
        self.client.force_authenticate(self.outsider)

        codes = [self.client.post(f'{ORGS}join/', {'invite_code': f'guess{i}'}).status_code
                 for i in range(11)]

        self.assertEqual(codes[-1], status.HTTP_429_TOO_MANY_REQUESTS)


class MemberManagementTests(OrgTestCase):
    def member_url(self, membership):
        return org_url(self.org, f'members/{membership.pk}/')

    def test_admin_promotes_member(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(self.member_url(self.member_membership), {'role': 'admin'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, 'admin')

    def test_member_cannot_manage_members(self):
        self.client.force_authenticate(self.member)

        response = self.client.delete(self.member_url(self.admin_membership))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_last_admin_cannot_demote_self(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(self.member_url(self.admin_membership), {'role': 'member'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_last_admin_cannot_leave(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(org_url(self.org, 'leave/'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.org.memberships.filter(user=self.admin).exists())

    def test_admin_can_leave_once_another_admin_exists(self):
        self.member_membership.role = Membership.Role.ADMIN
        self.member_membership.save()
        self.client.force_authenticate(self.admin)

        response = self.client.post(org_url(self.org, 'leave/'))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_member_can_leave(self):
        self.client.force_authenticate(self.member)

        response = self.client.post(org_url(self.org, 'leave/'))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.org.memberships.filter(user=self.member).exists())

    def test_members_list(self):
        self.client.force_authenticate(self.member)

        response = self.client.get(org_url(self.org, 'members/'))

        self.assertEqual([m['user']['username'] for m in response.data], ['admin1', 'member1'])
        self.assertEqual(response.data[0]['role'], 'admin')
