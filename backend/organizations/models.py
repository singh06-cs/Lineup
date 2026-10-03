import secrets

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


def generate_invite_code():
    # Module-level function (not a lambda) so migrations can reference it.
    return secrets.token_urlsafe(6)


class Organization(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    invite_code = models.CharField(max_length=16, unique=True, default=generate_invite_code)
    # Link to the club's page on Clubly (AggieWorks' UC Davis club finder). Restricted to
    # clubly.org so an org can't use this field to send members to an arbitrary site.
    clubly_url = models.URLField(
        blank=True,
        validators=[RegexValidator(
            r'^https://(www\.)?clubly\.org/[\w-]+/?$',
            'Use your club\'s Clubly page, e.g. https://clubly.org/mathclubatucdavis',
        )],
    )
    # Role differs per (user, org) pair, so it lives on the through model, not here or on User.
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Membership',
        related_name='organizations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'organization'],
                name='unique_membership',
                violation_error_message='This user is already a member of this organization.',
            ),
        ]

    def __str__(self):
        return f'{self.user} in {self.organization} ({self.role})'
