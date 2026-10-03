"""Everything that belongs on a user's calendar, in one format-neutral list.

Two outputs are built from this: the .ics feed (builder.py) and direct Google
Calendar sync (google_sync.py). Collecting once means both always agree on what a
user's calendar contains.

A class that meets 30 times a quarter is ONE event with a weekly recurrence that
ends with instruction and skips holidays, not 30 events.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from courses.models import Enrollment, Holiday, Meeting
from courses.services import campus_tz
from scheduling.models import ClubMeeting, Shift

# Python weekday number -> iCalendar day code
ICAL_DAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']


@dataclass
class Recurrence:
    weekdays: list[int]          # Monday=0
    until: datetime              # last moment, in UTC (RFC 5545 requires UTC with a zoned start)
    skipped: list[datetime] = field(default_factory=list)  # holiday occurrences, zoned

    @property
    def byday(self):
        return [ICAL_DAYS[day] for day in self.weekdays]


@dataclass
class CalendarEvent:
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str = ''
    description: str = ''
    recurrence: Recurrence | None = None


def first_day_on_or_after(start: date, weekdays):
    """First date >= start that falls on one of `weekdays` (Monday=0)."""
    for offset in range(7):
        day = start + timedelta(days=offset)
        if day.weekday() in weekdays:
            return day
    return None


def weekly_event(uid, summary, slot, term, holidays, description=''):
    """One recurring event for a WeeklySlot (class or club meeting) across a term."""
    tz = campus_tz()
    first = first_day_on_or_after(term.instruction_begins, slot.weekdays)
    if first is None or first > term.instruction_ends:
        return None
    # Times carry the campus zone, so "10:00 local" stays 10:00 across daylight saving.
    return CalendarEvent(
        uid=uid,
        summary=summary,
        start=datetime.combine(first, slot.start_time, tz),
        end=datetime.combine(first, slot.end_time, tz),
        location=slot.location,
        description=description,
        recurrence=Recurrence(
            weekdays=slot.weekdays,
            until=datetime.combine(term.instruction_ends, time(23, 59, 59), tz).astimezone(UTC),
            skipped=[
                datetime.combine(day, slot.start_time, tz)
                for day in sorted(holidays)
                if day.weekday() in slot.weekdays and first <= day <= term.instruction_ends
            ],
        ),
    )


def holidays_by_term(term_ids):
    result = {}
    for term_id, day in Holiday.objects.filter(term_id__in=term_ids).values_list('term_id', 'date'):
        result.setdefault(term_id, []).append(day)
    return result


def collect_events(user):
    meetings = list(
        Meeting.objects
        .filter(section__enrollments__user=user)
        .select_related('section__course', 'section__term')
    )
    club_meetings = list(
        ClubMeeting.objects
        .filter(organization__memberships__user=user)
        .select_related('organization', 'term')
    )
    holidays = holidays_by_term(
        {m.section.term_id for m in meetings} | {m.term_id for m in club_meetings}
    )
    events = []

    for meeting in meetings:
        section = meeting.section
        events.append(weekly_event(
            uid=f'meeting-{meeting.pk}@lineup',
            summary=f'{section.course} {meeting.get_kind_display()}',
            slot=meeting,
            term=section.term,
            holidays=holidays.get(section.term_id, []),
            description=f'{section.course.title}\nCRN {section.crn}'
                        + (f'\nInstructor: {section.instructor}' if section.instructor else ''),
        ))

    for enrollment in (
        Enrollment.objects
        .filter(user=user, section__final_exam_start__isnull=False)
        .select_related('section__course')
    ):
        section = enrollment.section
        events.append(CalendarEvent(
            uid=f'final-{section.pk}@lineup',
            summary=f'{section.course} Final Exam',
            start=section.final_exam_start,
            end=section.final_exam_end,
        ))

    for meeting in club_meetings:
        events.append(weekly_event(
            uid=f'club-meeting-{meeting.pk}@lineup',
            summary=f'{meeting.organization.name}: {meeting.title}',
            slot=meeting,
            term=meeting.term,
            holidays=holidays.get(meeting.term_id, []),
        ))

    for shift in Shift.objects.filter(signups__user=user).select_related('organization'):
        events.append(CalendarEvent(
            uid=f'shift-{shift.pk}@lineup',
            summary=f'{shift.organization.name}: {shift.title}',
            start=shift.start_time,
            end=shift.end_time,
            location=shift.location,
            description=shift.description,
        ))

    # weekly_event returns None for a slot that never falls inside its term.
    return [event for event in events if event is not None]
