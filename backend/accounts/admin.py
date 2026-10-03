from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

# UserAdmin gives the custom user the same admin pages as Django's built-in one
# (password hashing on change, permissions, groups).
admin.site.register(User, UserAdmin)
