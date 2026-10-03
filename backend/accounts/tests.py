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
