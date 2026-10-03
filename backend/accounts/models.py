from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Swapping the user model after the first migration is painful, so we
    # start with our own subclass even though it barely changes the default.
    email = models.EmailField(unique=True)


class GoogleIdentity(models.Model):
    """Links a Lineup account to a Google account, for "Sign in with Google".

    Matched by Google's `sub` (a permanent account ID), not by email: emails can
    change hands, `sub` never does.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_identity')
    sub = models.CharField(max_length=255, unique=True)
    email = models.EmailField()
    linked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} <-> Google {self.email}'
