from rest_framework import serializers

from accounts.serializers import UserSerializer
from organizations.models import Organization
from organizations.permissions import is_org_admin

from .models import Shift, Signup


class MyOrganizationField(serializers.PrimaryKeyRelatedField):
    # Only the user's own orgs are valid choices, so another org's id looks the same as a
    # nonexistent one ("Invalid pk") and doesn't reveal that it exists.
    def get_queryset(self):
        return Organization.objects.filter(members=self.context['request'].user)


class ShiftSerializer(serializers.ModelSerializer):
    organization = MyOrganizationField()
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    # Computed by annotate() in the view's queryset, never stored (derived data).
    signup_count = serializers.IntegerField(read_only=True)
    spots_left = serializers.IntegerField(read_only=True)
    is_signed_up = serializers.BooleanField(read_only=True)
    can_manage = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shift
        fields = [
            'id', 'organization', 'organization_name', 'title', 'description', 'location',
            'start_time', 'end_time', 'capacity', 'signup_count', 'spots_left',
            'is_signed_up', 'can_manage', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {'capacity': {'min_value': 1}}

    def validate_organization(self, organization):
        if self.instance and organization != self.instance.organization:
            raise serializers.ValidationError('A shift cannot be moved to another organization.')
        # Also stops non-members: you can't be an admin of an org you're not in.
        if not is_org_admin(self.context['request'].user, organization):
            raise serializers.ValidationError('You must be an admin of this organization.')
        return organization

    def validate(self, attrs):
        # On PATCH only some fields arrive, so fall back to the saved values.
        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'end_time': 'A shift must end after it starts.'})

        if self.instance and 'capacity' in attrs:
            taken = self.instance.signups.count()
            if attrs['capacity'] < taken:
                raise serializers.ValidationError({
                    'capacity': f'{taken} people are already signed up; capacity cannot go below that.',
                })
        return attrs


class RosterEntrySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Signup
        fields = ['id', 'user', 'created_at']
