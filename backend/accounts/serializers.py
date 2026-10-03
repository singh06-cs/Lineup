from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


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
