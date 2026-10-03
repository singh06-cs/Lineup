"""Builds a user's iCalendar (.ics) feed: classes, finals, club meetings and shifts.

A class that meets 30 times a quarter is ONE event with a recurrence rule, not 30
events:  RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=<last day of instruction>
plus EXDATE lines for holidays. The calendar app expands it, so editing a class
time in Lineup moves every occurrence at once.
"""

from datetime import UTC, datetime, time, timedelta

from django.utils import timezone
from icalendar import Calendar, Event

from courses.models import Enrollment, Holiday, Meeting
from courses.services import campus_tz
from scheduling.models import ClubMeeting, Shift

# Python weekday number -> iCalendar day code
ICAL_DAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']


def first_day_on_or_after(start, weekdays):
    """First date >= start that falls on one of `weekdays` (Monday=0)."""
    for offset in range(7):
        day = start + timedelta(days=offset)
        if day.weekday() in weekdays:
            return day
    return None


def weekly_event(uid, summary, slot, term, holidays, description=''):
    """One recurring event for a WeeklySlot (class meeting or club meeting) across a term."""
    tz = campus_tz()
    first = first_day_on_or_after(term.instruction_begins, slot.weekdays)
    if first is None or first > term.instruction_ends:
        return None

    event = Event()
    event.add('uid', uid)
    event.add('summary', summary)
    # Times carry the campus zone (TZID=America/Los_Angeles), so the calendar keeps
    # "10:00 local" across the daylight-saving change instead of shifting an hour.
    event.add('dtstart', datetime.combine(first, slot.start_time, tz))
    event.add('dtend', datetime.combine(first, slot.end_time, tz))
    # RFC 5545: with a zoned DTSTART, UNTIL must be given in UTC.
    until = datetime.combine(term.instruction_ends, time(23, 59, 59), tz).astimezone(UTC)
    event.add('rrule', {
        'freq': 'weekly',
        'byday': [ICAL_DAYS[day] for day in slot.weekdays],
        'until': until,
    })
    skipped = [
        datetime.combine(day, slot.start_time, tz)
        for day in holidays
        if day.weekday() in slot.weekdays and first <= day <= term.instruction_ends
    ]
    if skipped:
        event.add('exdate', skipped)
    if slot.location:
        event.add('location', slot.location)
    if description:
        event.add('description', description)
    event.add('dtstamp', timezone.now())
    return event


def single_event(uid, summary, start, end, location='', description=''):
    event = Event()
    event.add('uid', uid)
    event.add('summary', summary)
    event.add('dtstart', start)
    event.add('dtend', end)
    if location:
        event.add('location', location)
    if description:
        event.add('description', description)
    event.add('dtstamp', timezone.now())
    return event


def holidays_by_term(term_ids):
    result = {}
    for term_id, day in Holiday.objects.filter(term_id__in=term_ids).values_list('term_id', 'date'):
        result.setdefault(term_id, []).append(day)
    return result


def build_calendar(user):
    cal = Calendar()
    cal.add('prodid', '-//Lineup//Lineup//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', 'Lineup')
    cal.add('x-wr-timezone', str(campus_tz()))

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

    for meeting in meetings:
        section = meeting.section
        event = weekly_event(
            uid=f'meeting-{meeting.pk}@lineup',
            summary=f'{section.course} {meeting.get_kind_display()}',
            slot=meeting,
            term=section.term,
            holidays=holidays.get(section.term_id, []),
            description=f'{section.course.title}\nCRN {section.crn}'
                        + (f'\nInstructor: {section.instructor}' if section.instructor else ''),
        )
        if event:
            cal.add_component(event)

    for enrollment in (
        Enrollment.objects
        .filter(user=user, section__final_exam_start__isnull=False)
        .select_related('section__course')
    ):
        section = enrollment.section
        cal.add_component(single_event(
            uid=f'final-{section.pk}@lineup',
            summary=f'{section.course} Final Exam',
            start=section.final_exam_start,
            end=section.final_exam_end,
        ))

    for meeting in club_meetings:
        event = weekly_event(
            uid=f'club-meeting-{meeting.pk}@lineup',
            summary=f'{meeting.organization.name}: {meeting.title}',
            slot=meeting,
            term=meeting.term,
            holidays=holidays.get(meeting.term_id, []),
        )
        if event:
            cal.add_component(event)

    for shift in Shift.objects.filter(signups__user=user).select_related('organization'):
        cal.add_component(single_event(
            uid=f'shift-{shift.pk}@lineup',
            summary=f'{shift.organization.name}: {shift.title}',
            start=shift.start_time,
            end=shift.end_time,
            location=shift.location,
            description=shift.description,
        ))

    # Adds the VTIMEZONE block describing America/Los_Angeles (incl. its DST rules),
    # which calendar apps need to interpret TZID=America/Los_Angeles correctly.
    cal.add_missing_timezones()
    return cal.to_ical()
