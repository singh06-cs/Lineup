from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    # Both come from annotate() in the view's queryset, so listing orgs stays one query.
    member_count = serializers.IntegerField(read_only=True)
    my_role = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'name', 'description', 'invite_code', 'member_count', 'my_role', 'created_at']
        read_only_fields = ['id', 'invite_code', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Anyone holding the invite code can join, so only admins get to see it.
        if getattr(instance, 'my_role', None) != Membership.Role.ADMIN:
            data.pop('invite_code')
        return data


class JoinOrganizationSerializer(serializers.Serializer):
    invite_code = serializers.CharField(max_length=16)


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'joined_at']
        read_only_fields = ['id', 'user', 'joined_at']
