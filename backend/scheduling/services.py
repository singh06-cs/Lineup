"""Signup business rules.

Kept out of the view so the rules live in one place and can be tested and reused
(e.g. by a future swap-request feature) without going through HTTP.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from courses.services import class_conflicts

from .models import Shift, Signup

User = get_user_model()


def sign_up(user, shift):
    with transaction.atomic():
        # Row locks make concurrent signups wait their turn instead of all reading
        # "1 spot left" at once. Lock the user first, then the shift, in every code
        # path: a consistent order means two requests can never deadlock each other.
        # - User lock: serializes one person's signups (overlap check).
        # - Shift lock: serializes everyone's signups for this shift (capacity check).
        User.objects.select_for_update().get(pk=user.pk)
        shift = Shift.objects.select_for_update().get(pk=shift.pk)

        if shift.start_time <= timezone.now():
            raise ValidationError({'detail': 'This shift has already started.'}, code='started')

        if shift.signups.filter(user=user).exists():
            raise ValidationError(
                {'detail': 'You are already signed up for this shift.'}, code='duplicate',
            )

        if shift.signups.count() >= shift.capacity:
            raise ValidationError({'detail': 'This shift is full.'}, code='full')

        # Two ranges overlap iff A.start < B.end and A.end > B.start.
        # Checked across all orgs: you can't be in two places at once.
        clash = (
            Signup.objects
            .filter(
                user=user,
                shift__start_time__lt=shift.end_time,
                shift__end_time__gt=shift.start_time,
            )
            .select_related('shift')
            .first()
        )
        if clash:
            raise ValidationError(
                {'detail': f'This overlaps with "{clash.shift.title}", which you are already signed up for.'},
                code='overlap',
            )

        # Classes come first: a volunteer shift can't overlap a class or final exam.
        busy = class_conflicts(user, shift.start_time, shift.end_time)
        if busy:
            raise ValidationError(
                {'detail': f'This shift overlaps your class: {busy[0]}.'}, code='class_conflict',
            )

        return Signup.objects.create(user=user, shift=shift)


def shifts_conflicting_with_classes(user):
    """The user's upcoming shifts that clash with their class schedule.

    Enrolling in a class isn't blocked by a shift you already signed up for, so this
    lets the app warn you to cancel the shift instead.
    """
    upcoming = (
        Shift.objects
        .filter(signups__user=user, end_time__gt=timezone.now())
        .select_related('organization')
    )
    results = []
    for shift in upcoming:
        busy = class_conflicts(user, shift.start_time, shift.end_time)
        if busy:
            results.append({'shift': shift, 'conflicts': busy})
    return results


def cancel_signup(user, shift):
    if shift.start_time <= timezone.now():
        raise ValidationError(
            {'detail': 'You cannot cancel a shift that has already started.'}, code='started',
        )
    deleted, _ = Signup.objects.filter(user=user, shift=shift).delete()
    if not deleted:
        raise ValidationError({'detail': 'You are not signed up for this shift.'}, code='not_signed_up')
