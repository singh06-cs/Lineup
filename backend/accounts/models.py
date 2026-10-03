from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Swapping the user model after the first migration is painful, so we
    # start with our own subclass even though it barely changes the default.
    email = models.EmailField(unique=True)
