from rest_framework import permissions

from .models import Membership


def is_org_admin(user, organization):
    return Membership.objects.filter(
        user=user, organization=organization, role=Membership.Role.ADMIN,
    ).exists()


class IsOrgAdmin(permissions.BasePermission):
    """Object-level check: the user is an admin of this organization.

    Membership itself is enforced earlier by scoping get_queryset() to the user's
    orgs, so non-members get a 404 before this ever runs.
    """

    message = 'Only organization admins can do this.'

    def has_object_permission(self, request, view, obj):
        return is_org_admin(request.user, obj)
