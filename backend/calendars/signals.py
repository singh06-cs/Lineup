"""Keeps Google Calendar in sync when anything on someone's calendar changes.

Signals let calendars react to saves in courses/scheduling/organizations WITHOUT
those apps importing calendars, so the one-way dependency rule still holds.
Note: bulk_create() and queryset.update() skip signals; the paths that use
bulk_create (new sections, seed data) are followed by a save that does fire one.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from courses.models import Enrollment, Meeting, Section
from organizations.models import Membership
from scheduling.models import ClubMeeting, Shift, Signup

from .google_sync import request_sync


@receiver([post_save, post_delete], sender=Enrollment)
@receiver([post_save, post_delete], sender=Signup)
@receiver([post_save, post_delete], sender=Membership)
def personal_change(sender, instance, **kwargs):
    request_sync([instance.user_id])


@receiver(post_save, sender=Shift)
def shift_changed(sender, instance, **kwargs):
    request_sync(Signup.objects.filter(shift=instance).values_list('user_id', flat=True))


@receiver(post_save, sender=Section)
def section_changed(sender, instance, **kwargs):
    request_sync(Enrollment.objects.filter(section=instance).values_list('user_id', flat=True))


@receiver([post_save, post_delete], sender=Meeting)
def class_meeting_changed(sender, instance, **kwargs):
    request_sync(Enrollment.objects.filter(section_id=instance.section_id).values_list('user_id', flat=True))


@receiver([post_save, post_delete], sender=ClubMeeting)
def club_meeting_changed(sender, instance, **kwargs):
    request_sync(
        Membership.objects.filter(organization_id=instance.organization_id).values_list('user_id', flat=True)
    )
