from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import Membership, Organization, generate_invite_code
from .permissions import IsOrgAdmin
from .serializers import (
    JoinOrganizationSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)


def ensure_admin_remains(organization, membership):
    """Reject losing the org's last admin. Caller must hold the org's row lock."""
    if (
        membership.role == Membership.Role.ADMIN
        and organization.memberships.filter(role=Membership.Role.ADMIN).count() == 1
    ):
        raise serializers.ValidationError(
            'An organization must keep at least one admin. Promote someone else first.'
        )


def lock_organization(organization):
    # Row lock so two admins demoting each other at the same time can't leave zero admins.
    return Organization.objects.select_for_update().get(pk=organization.pk)


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    admin_actions = {'update', 'partial_update', 'destroy', 'member_detail', 'regenerate_invite_code'}

    def get_queryset(self):
        user = self.request.user
        my_memberships = Membership.objects.filter(user=user)
        # Filtering by a subquery (not memberships__user=user) keeps member_count correct:
        # filtering through the same join would make Count() see only the user's own row.
        return (
            Organization.objects
            .filter(pk__in=my_memberships.values('organization_id'))
            .annotate(
                member_count=Count('memberships'),
                my_role=Subquery(
                    my_memberships.filter(organization=OuterRef('pk')).values('role')[:1]
                ),
            )
            # Explicit: Meta.ordering is dropped in GROUP BY (Count) queries, which
            # would make pagination order unpredictable.
            .order_by('name', 'pk')
        )

    def get_permissions(self):
        if self.action in self.admin_actions:
            return [permissions.IsAuthenticated(), IsOrgAdmin()]
        return [permissions.IsAuthenticated()]

    def get_throttles(self):
        # Invite codes are guessable by brute force without a rate limit.
        if self.action == 'join':
            self.throttle_scope = 'join'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def respond_with_org(self, organization, status_code=status.HTTP_200_OK):
        # Re-read through get_queryset() so the response includes the annotated fields.
        organization = self.get_queryset().get(pk=organization.pk)
        return Response(self.get_serializer(organization).data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Both rows or neither: an org must never exist without an admin.
        with transaction.atomic():
            organization = serializer.save()
            Membership.objects.create(
                user=request.user, organization=organization, role=Membership.Role.ADMIN,
            )
        return self.respond_with_org(organization, status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def join(self, request):
        serializer = JoinOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(
            Organization, invite_code=serializer.validated_data['invite_code'],
        )
        if organization.memberships.filter(user=request.user).exists():
            raise serializers.ValidationError('You are already a member of this organization.')
        Membership.objects.create(user=request.user, organization=organization)
        return self.respond_with_org(organization, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        organization = self.get_object()
        with transaction.atomic():
            organization = lock_organization(organization)
            membership = organization.memberships.get(user=request.user)
            ensure_admin_remains(organization, membership)
            membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='regenerate-invite-code')
    def regenerate_invite_code(self, request, pk=None):
        # Lets an admin revoke a code that leaked; the old one stops working immediately.
        organization = self.get_object()
        organization.invite_code = generate_invite_code()
        organization.save(update_fields=['invite_code'])
        return self.respond_with_org(organization)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        organization = self.get_object()
        memberships = organization.memberships.select_related('user').order_by('joined_at')
        return Response(MembershipSerializer(memberships, many=True).data)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'members/(?P<membership_id>\d+)')
    def member_detail(self, request, pk=None, membership_id=None):
        """Admins change a member's role (PATCH) or remove them (DELETE)."""
        organization = self.get_object()
        with transaction.atomic():
            organization = lock_organization(organization)
            membership = get_object_or_404(organization.memberships, pk=membership_id)

            if request.method == 'DELETE':
                ensure_admin_remains(organization, membership)
                membership.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)

            serializer = MembershipSerializer(membership, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data.get('role') == Membership.Role.MEMBER:
                ensure_admin_remains(organization, membership)
            serializer.save()
        return Response(serializer.data)
