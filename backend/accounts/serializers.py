from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class MeSerializer(UserSerializer):
    """The logged-in user's own profile, plus how they can sign in."""

    google_linked = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['google_linked', 'has_password']

    def get_google_linked(self, user):
        return hasattr(user, 'google_identity')

    def get_has_password(self, user):
        return user.has_usable_password()


class GoogleCredentialSerializer(serializers.Serializer):
    credential = serializers.CharField()


class RegisterSerializer(serializers.ModelSerializer):
    # write_only: accepted on input, never included in a response
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']
        read_only_fields = ['id']

    def validate_password(self, value):
        # Same rules as createsuperuser: length, common passwords, all-numeric, similarity
        validate_password(value)
        return value

    def create(self, validated_data):
        # create_user() hashes the password; objects.create() would store it as plain text
        return User.objects.create_user(**validated_data)


class SafeTokenRefreshSerializer(TokenRefreshSerializer):
    """SimpleJWT's refresh, but a token whose user was deleted gets a 401, not a 500.

    The library looks the user up and doesn't catch DoesNotExist, so refreshing a
    token after the account is gone crashed the request.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except User.DoesNotExist:
            raise InvalidToken('This account no longer exists.')
