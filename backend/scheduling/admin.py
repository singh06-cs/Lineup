from django.contrib import admin
from django.db.models import Count

from .models import ClubMeeting, Shift, Signup


class SignupInline(admin.TabularInline):
    model = Signup
    extra = 0
    autocomplete_fields = ['user']
    readonly_fields = ['created_at']


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['title', 'organization', 'start_time', 'end_time', 'filled', 'capacity']
    list_filter = ['organization', 'start_time']
    search_fields = ['title', 'location', 'organization__name']
    date_hierarchy = 'start_time'
    autocomplete_fields = ['organization', 'created_by']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    list_select_related = ['organization']
    inlines = [SignupInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(signup_count=Count('signups'))

    @admin.display(description='Filled', ordering='signup_count')
    def filled(self, obj):
        return obj.signup_count

    def save_model(self, request, obj, form, change):
        # Record who created the shift; the admin form doesn't expose this field.
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Signup)
class SignupAdmin(admin.ModelAdmin):
    list_display = ['user', 'shift', 'created_at']
    list_filter = ['shift__organization']
    search_fields = ['user__username', 'shift__title']
    autocomplete_fields = ['user', 'shift']
    list_select_related = ['user', 'shift']


@admin.register(ClubMeeting)
class ClubMeetingAdmin(admin.ModelAdmin):
    list_display = ['organization', 'title', 'term', 'days', 'start_time', 'end_time', 'location']
    list_filter = ['term', 'organization']
    autocomplete_fields = ['organization']
