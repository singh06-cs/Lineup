from rest_framework import permissions

from organizations.permissions import is_org_admin


class IsOrgAdminOfObject(permissions.BasePermission):
    """For any object with an .organization (shifts, club meetings)."""

    message = 'Only admins of this organization can manage this.'

    def has_object_permission(self, request, view, obj):
        return is_org_admin(request.user, obj.organization)
