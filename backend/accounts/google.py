"""Verifies the ID token the browser gets from Google's "Sign in with Google" button."""

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class GoogleSignInError(Exception):
    pass


def google_sign_in_enabled():
    return bool(settings.GOOGLE_CLIENT_ID)


def verify_google_credential(credential):
    """Check the token's signature, issuer, expiry and audience, then return who it is.

    The audience check matters: it proves the token was issued for OUR client ID, so a
    token some other website obtained for its own app can't be replayed against Lineup.
    """
    try:
        info = id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise GoogleSignInError('Google sign-in failed. Please try again.') from exc
    if not info.get('email_verified'):
        raise GoogleSignInError('Your Google account email is not verified.')
    return {
        'sub': info['sub'],
        'email': info['email'].lower(),
        'first_name': info.get('given_name', ''),
        'last_name': info.get('family_name', ''),
    }
