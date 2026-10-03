from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    # Opt out of the global IsAuthenticated default: you can't be logged in before signing up
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

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
