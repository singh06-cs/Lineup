from rest_framework import permissions


class IsCreatorOrStaff(permissions.BasePermission):
    """Shared catalog: whoever added a section (or staff) may change it."""

    message = 'Only the person who added this section can change it.'

    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.created_by_id == request.user.id
