from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = 'correct-horse-battery'


class RegisterTests(APITestCase):
    url = reverse('register')

    def test_register_creates_user_with_hashed_password(self):
        response = self.client.post(self.url, {
            'username': 'alice', 'email': 'alice@example.com', 'password': PASSWORD,
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.data)
        user = User.objects.get(username='alice')
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_weak_password_rejected(self):
        response = self.client.post(self.url, {
            'username': 'alice', 'email': 'alice@example.com', 'password': '123456',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_duplicate_email_rejected(self):
        User.objects.create_user('bob', 'shared@example.com', PASSWORD)

        response = self.client.post(self.url, {
            'username': 'alice', 'email': 'shared@example.com', 'password': PASSWORD,
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)


class TokenFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', PASSWORD)

    def login(self):
        response = self.client.post(reverse('login'), {'username': 'alice', 'password': PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(reverse('login'), {'username': 'alice', 'password': 'nope'})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_with_access_token(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'alice')

    def test_refresh_rotates_and_old_refresh_token_is_rejected(self):
        tokens = self.login()

        first = self.client.post(reverse('token-refresh'), {'refresh': tokens['refresh']})
        reused = self.client.post(reverse('token-refresh'), {'refresh': tokens['refresh']})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIn('access', first.data)
        self.assertNotEqual(first.data['refresh'], tokens['refresh'])
        self.assertEqual(reused.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        logout = self.client.post(reverse('logout'), {'refresh': tokens['refresh']})
        refresh = self.client.post(reverse('token-refresh'), {'refresh': tokens['refresh']})

        self.assertEqual(logout.status_code, status.HTTP_205_RESET_CONTENT)
        self.assertEqual(refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_after_account_deleted_is_401_not_500(self):
        tokens = self.login()
        self.user.delete()

        response = self.client.post(reverse('token-refresh'), {'refresh': tokens['refresh']})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------- Phase 19: Sign in with Google ----------

from unittest.mock import patch  # noqa: E402

from django.test import override_settings  # noqa: E402

from .google import GoogleSignInError, verify_google_credential  # noqa: E402
from .models import GoogleIdentity  # noqa: E402

GOOGLE = '/api/auth/google/'
GOOGLE_USER = {'sub': 'google-sub-123', 'email': 'maya@gmail.com', 'first_name': 'Maya', 'last_name': 'Lee'}


@override_settings(GOOGLE_CLIENT_ID='test-client-id.apps.googleusercontent.com')
class GoogleSignInTests(APITestCase):
    def google_post(self, info=GOOGLE_USER):
        with patch('accounts.views.verify_google_credential', return_value=info):
            return self.client.post(GOOGLE, {'credential': 'signed-id-token-from-google'})

    def test_config_tells_frontend_whether_to_show_the_button(self):
        data = self.client.get('/api/auth/google/config/').data
        self.assertEqual(data, {'enabled': True, 'client_id': 'test-client-id.apps.googleusercontent.com'})

        with override_settings(GOOGLE_CLIENT_ID=''):
            self.assertFalse(self.client.get('/api/auth/google/config/').data['enabled'])
            self.assertEqual(self.google_post().status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_first_google_sign_in_creates_account_without_a_password(self):
        response = self.google_post()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        user = User.objects.get(email='maya@gmail.com')
        self.assertEqual((user.username, user.first_name), ('maya', 'Maya'))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.google_identity.sub, 'google-sub-123')

    def test_returning_user_matched_by_google_id_not_email(self):
        self.google_post()

        # Same Google account, new email address: still the same Lineup user.
        response = self.google_post({**GOOGLE_USER, 'email': 'maya.new@gmail.com'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.count(), 1)

    def test_existing_password_account_is_not_silently_taken_over(self):
        User.objects.create_user('maya_pw', 'maya@gmail.com', PASSWORD)

        response = self.google_post()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(GoogleIdentity.objects.exists())

    def test_username_collision_gets_a_suffix(self):
        User.objects.create_user('maya', 'someone.else@example.com', PASSWORD)

        self.google_post()

        self.assertTrue(User.objects.filter(username='maya2', email='maya@gmail.com').exists())

    def test_bad_token_rejected(self):
        with patch('accounts.views.verify_google_credential', side_effect=GoogleSignInError('nope')):
            response = self.client.post(GOOGLE, {'credential': 'forged'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_link_and_unlink_from_a_password_account(self):
        user = User.objects.create_user('maya_pw', 'maya@school.edu', PASSWORD)
        self.client.force_authenticate(user)

        linked = self.google_post()
        self.assertEqual(linked.status_code, status.HTTP_200_OK)
        self.assertTrue(linked.data['google_linked'])

        unlinked = self.client.delete(GOOGLE)
        self.assertFalse(unlinked.data['google_linked'])

    def test_cannot_link_a_google_account_someone_else_uses(self):
        self.google_post()  # creates the Google user
        other = User.objects.create_user('other', 'other@example.com', PASSWORD)
        self.client.force_authenticate(other)

        self.assertEqual(self.google_post().status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_only_account_cannot_unlink_its_only_sign_in(self):
        self.google_post()
        self.client.force_authenticate(User.objects.get(email='maya@gmail.com'))

        response = self.client.delete(GOOGLE)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(GoogleIdentity.objects.exists())


@override_settings(GOOGLE_CLIENT_ID='test-client-id.apps.googleusercontent.com')
class VerifyGoogleCredentialTests(APITestCase):
    """Our wrapper around Google's verifier (the library call itself is mocked)."""

    def test_invalid_signature_or_audience_becomes_a_friendly_error(self):
        with patch('accounts.google.id_token.verify_oauth2_token', side_effect=ValueError('Wrong audience')):
            with self.assertRaises(GoogleSignInError):
                verify_google_credential('token-for-another-app')

    def test_unverified_email_rejected(self):
        claims = {'sub': '1', 'email': 'x@gmail.com', 'email_verified': False}
        with patch('accounts.google.id_token.verify_oauth2_token', return_value=claims):
            with self.assertRaises(GoogleSignInError):
                verify_google_credential('token')

    def test_verified_token_passes_our_client_id_as_audience(self):
        claims = {'sub': '1', 'email': 'X@Gmail.com', 'email_verified': True, 'given_name': 'X'}
        with patch('accounts.google.id_token.verify_oauth2_token', return_value=claims) as verify:
            info = verify_google_credential('token')

        self.assertEqual(verify.call_args.args[2], 'test-client-id.apps.googleusercontent.com')
        self.assertEqual(info['email'], 'x@gmail.com')
