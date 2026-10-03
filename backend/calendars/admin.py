from django.contrib import admin

from .models import GoogleCalendarConnection


@admin.register(GoogleCalendarConnection)
class GoogleCalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'google_email', 'last_synced_at', 'last_error']
    search_fields = ['user__username', 'google_email']
    # Never show the (encrypted) refresh token, even to staff.
    exclude = ['encrypted_refresh_token']
    readonly_fields = ['user', 'google_email', 'calendar_id', 'connected_at', 'last_synced_at', 'last_error']
