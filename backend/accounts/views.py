import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .google import GoogleSignInError, google_sign_in_enabled, verify_google_credential
from .models import GoogleIdentity
from .serializers import GoogleCredentialSerializer, MeSerializer, RegisterSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    # Opt out of the global IsAuthenticated default: you can't be logged in before signing up
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer

    def get_object(self):
        # No id in the URL: you can only ever read or edit yourself
        return self.request.user


class LogoutView(APIView):
    def post(self, request):
        # JWTs can't be "deleted" server-side, so logout blacklists the refresh token.
        # The short-lived access token simply expires on its own.
        try:
            RefreshToken(request.data.get('refresh')).blacklist()
        except TokenError:
            raise serializers.ValidationError({'refresh': 'Invalid or expired token.'})
        return Response(status=status.HTTP_205_RESET_CONTENT)


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def unique_username(email):
    base = re.sub(r'[^\w.+-]', '', email.split('@')[0])[:140] or 'student'
    username, n = base, 1
    while User.objects.filter(username__iexact=username).exists():
        n += 1
        username = f'{base}{n}'
    return username


class GoogleConfigView(APIView):
    """Tells the frontend whether to show Google buttons, and with which client ID.

    A client ID is public by design (it's in every page that shows the button);
    the client SECRET never leaves the server.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'enabled': google_sign_in_enabled(),
            'client_id': settings.GOOGLE_CLIENT_ID or None,
        })


class GoogleAuthView(APIView):
    """POST a Google ID token.

    - Logged out: sign in (or sign up) with Google, get Lineup tokens back.
    - Logged in: link Google to your current account.
    DELETE (logged in): unlink Google.
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def post(self, request):
        if not google_sign_in_enabled():
            return Response({'detail': 'Google sign-in is not set up.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = GoogleCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            google = verify_google_credential(serializer.validated_data['credential'])
        except GoogleSignInError as exc:
            raise serializers.ValidationError({'detail': str(exc)})

        if request.user.is_authenticated:
            return self.link(request.user, google)
        return self.sign_in(google)

    def link(self, user, google):
        existing = GoogleIdentity.objects.filter(sub=google['sub']).first()
        if existing and existing.user_id != user.id:
            raise serializers.ValidationError({'detail': 'That Google account is linked to a different Lineup account.'})
        if hasattr(user, 'google_identity') and user.google_identity.sub != google['sub']:
            raise serializers.ValidationError({'detail': 'Unlink your current Google account first.'})
        GoogleIdentity.objects.get_or_create(user=user, defaults={'sub': google['sub'], 'email': google['email']})
        return Response(MeSerializer(user).data)

    def sign_in(self, google):
        identity = GoogleIdentity.objects.select_related('user').filter(sub=google['sub']).first()
        if identity:
            return Response(tokens_for(identity.user))

        # Not auto-linked on a matching email: Lineup doesn't verify emails at sign-up,
        # so someone could register a password account with YOUR email in advance and
        # keep access after you "sign in with Google" ("pre-account hijacking").
        if User.objects.filter(email__iexact=google['email']).exists():
            return Response(
                {'detail': 'An account with this email already exists. Log in with your password, '
                           'then link Google from your Account page.'},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            user = User(
                username=unique_username(google['email']),
                email=google['email'],
                first_name=google['first_name'],
                last_name=google['last_name'],
            )
            user.set_unusable_password()  # Google-only account: there is no password to guess
            user.save()
            GoogleIdentity.objects.create(user=user, sub=google['sub'], email=google['email'])
        return Response(tokens_for(user), status=status.HTTP_201_CREATED)

    def delete(self, request):
        user = request.user
        if not user.has_usable_password():
            raise serializers.ValidationError(
                {'detail': 'Google is your only way to sign in. Set a password before unlinking it.'}
            )
        GoogleIdentity.objects.filter(user=user).delete()
        # Re-read: the user object may still have the deleted link cached on it.
        return Response(MeSerializer(User.objects.get(pk=user.pk)).data)
