from django.contrib import admin
from django.db.models import Count

from .models import Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ['user']
    readonly_fields = ['joined_at']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'member_count', 'invite_code', 'created_at']
    search_fields = ['name']
    readonly_fields = ['invite_code', 'created_at']
    inlines = [MembershipInline]

    def get_queryset(self, request):
        # Count members in the same query instead of one extra query per row (N+1).
        return super().get_queryset(request).annotate(member_count=Count('memberships'))

    @admin.display(description='Members', ordering='member_count')
    def member_count(self, obj):
        return obj.member_count


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'joined_at']
    list_filter = ['role', 'organization']
    search_fields = ['user__username', 'user__email', 'organization__name']
    autocomplete_fields = ['user', 'organization']
    # Fetch user and organization with a JOIN so each row doesn't trigger 2 extra queries.
    list_select_related = ['user', 'organization']
