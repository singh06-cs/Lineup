"""Schedule rules: enrolling, dropping, and detecting time conflicts.

Classes repeat weekly in campus local time; shifts are one-off UTC instants. The
functions here are the bridge between the two.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Enrollment, Meeting, Section

User = get_user_model()


def weekly_meetings_overlap(a, b):
    """Two weekly slots clash if they share a weekday and their times overlap.

    Same interval formula as shifts: A.start < B.end and A.end > B.start.
    """
    return (
        bool(set(a.days) & set(b.days))
        and a.start_time < b.end_time
        and a.end_time > b.start_time
    )


def schedule_conflicts(user, section):
    """(new meeting, existing meeting) pairs that clash with the user's other classes this term."""
    existing = list(
        Meeting.objects
        .filter(section__enrollments__user=user, section__term_id=section.term_id)
        .exclude(section=section)
        .select_related('section__course')
    )
    return [
        (new, old)
        for new in section.meetings.all()
        for old in existing
        if weekly_meetings_overlap(new, old)
    ]


def enroll(user, section):
    with transaction.atomic():
        # Lock the user so two enroll requests can't both pass the conflict check.
        User.objects.select_for_update().get(pk=user.pk)

        if Enrollment.objects.filter(user=user, section=section).exists():
            raise ValidationError({'detail': 'This section is already on your schedule.'})

        same_course = (
            Enrollment.objects
            .filter(user=user, section__term_id=section.term_id, section__course_id=section.course_id)
            .select_related('section')
            .first()
        )
        if same_course:
            raise ValidationError({
                'detail': f'You already have {section.course} section '
                          f'{same_course.section.section_code or same_course.section.crn}. Drop it first.',
            })

        clashes = schedule_conflicts(user, section)
        if clashes:
            described = '; '.join(old.describe() for _, old in clashes)
            raise ValidationError({'detail': f'Time conflict with {described}.'})

        return Enrollment.objects.create(user=user, section=section)


def drop(user, section):
    deleted, _ = Enrollment.objects.filter(user=user, section=section).delete()
    if not deleted:
        raise ValidationError({'detail': 'This section is not on your schedule.'})

