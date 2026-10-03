"""Schedule rules: enrolling, dropping, and detecting time conflicts.

Classes repeat weekly in campus local time; shifts are one-off UTC instants. The
functions here are the bridge between the two.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Enrollment, Holiday, Meeting, Section

User = get_user_model()


def campus_tz():
    return ZoneInfo(settings.CAMPUS_TIME_ZONE)


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


def class_conflicts(user, start, end, sections=None):
    """Class meetings and finals that fall inside the instant range [start, end).

    `start`/`end` are timezone-aware datetimes (e.g. a shift). Each weekly meeting is
    expanded onto the actual campus-local calendar days in that range, skipping days
    outside instruction and holidays. Returns human-readable descriptions.

    `sections` limits the check (e.g. to one section being enrolled); by default it's
    every section on the user's schedule.
    """
    if sections is None:
        sections = Section.objects.filter(enrollments__user=user)
    tz = campus_tz()
    local_start, local_end = start.astimezone(tz), end.astimezone(tz)

    meetings = list(
        Meeting.objects
        .filter(
            section__in=sections,
            section__term__instruction_begins__lte=local_end.date(),
            section__term__instruction_ends__gte=local_start.date(),
        )
        .select_related('section__course', 'section__term')
    )
    term_ids = {m.section.term_id for m in meetings}
    holidays = set(Holiday.objects.filter(term_id__in=term_ids).values_list('term_id', 'date'))

    conflicts = []
    day = local_start.date()
    while day <= local_end.date():
        # combine() with the zone resolves daylight saving correctly for that day:
        # "10:00 on Nov 2" is 18:00 UTC, while "10:00 on Oct 26" is 17:00 UTC.
        for meeting in meetings:
            term = meeting.section.term
            if not term.instruction_begins <= day <= term.instruction_ends:
                continue
            if (term.id, day) in holidays or day.weekday() not in meeting.weekdays:
                continue
            meeting_start = datetime.combine(day, meeting.start_time, tz)
            meeting_end = datetime.combine(day, meeting.end_time, tz)
            if meeting_start < local_end and meeting_end > local_start:
                conflicts.append(f'{meeting.describe()} on {day:%a %b} {day.day}')
        day += timedelta(days=1)

    finals = sections.filter(final_exam_start__lt=end, final_exam_end__gt=start).select_related('course')
    conflicts.extend(f'{section.course} final exam' for section in finals)
    return conflicts


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

