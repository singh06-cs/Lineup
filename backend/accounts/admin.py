from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import GoogleIdentity, User

# UserAdmin gives the custom user the same admin pages as Django's built-in one
# (password hashing on change, permissions, groups).
admin.site.register(User, UserAdmin)


@admin.register(GoogleIdentity)
class GoogleIdentityAdmin(admin.ModelAdmin):
    list_display = ['user', 'email', 'linked_at']
    search_fields = ['user__username', 'email']
    readonly_fields = ['user', 'sub', 'email', 'linked_at']
