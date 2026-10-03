from rest_framework import permissions

from organizations.permissions import is_org_admin


class IsShiftOrgAdmin(permissions.BasePermission):
    message = 'Only admins of this organization can manage its shifts.'

    def has_object_permission(self, request, view, obj):
        return is_org_admin(request.user, obj.organization)
