from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from organizations.models import Organization

from .management.commands.seed_demo import DEMO_PASSWORD
from .models import Shift

User = get_user_model()


class DemoSeedTests(TestCase):
    def seed(self, *args):
        call_command('seed_demo', *args, stdout=StringIO())

    @override_settings(DEBUG=False, DEMO_MODE=False)
    def test_normal_production_rejects_demo_accounts(self):
        with self.assertRaises(CommandError):
            self.seed('--if-empty')
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False, DEMO_MODE=True)
    def test_public_demo_seeds_nonstaff_accounts_without_debug(self):
        self.seed('--if-empty')
        for username in ('demo_student', 'demo_admin'):
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(DEMO_PASSWORD))
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
        self.assertEqual(Organization.objects.count(), 2)
        self.assertTrue(Shift.objects.exists())

    @override_settings(DEBUG=False, DEMO_MODE=True)
    def test_redeploy_preserves_changes_to_demo_data(self):
        self.seed('--if-empty')
        shift = Shift.objects.first()
        shift.title = 'Reviewer changed this title'
        shift.save()
        self.seed('--if-empty')
        shift.refresh_from_db()
        self.assertEqual(shift.title, 'Reviewer changed this title')
        self.assertEqual(User.objects.count(), 2)

    @override_settings(DEBUG=False, DEMO_MODE=True)
    def test_existing_user_prevents_seeding(self):
        user = User.objects.create_user('existing_user', 'existing@example.com')
        self.seed('--if-empty')
        self.assertEqual(list(User.objects.values_list('pk', flat=True)), [user.pk])
        self.assertFalse(Organization.objects.exists())

    @override_settings(DEBUG=True, DEMO_MODE=False)
    def test_development_seeding_still_works(self):
        self.seed()
        self.assertTrue(User.objects.filter(username='demo_student').exists())
