"""Formats a user's events (events.py) as an iCalendar (.ics) feed."""

from django.utils import timezone
from icalendar import Calendar, Event

from courses.services import campus_tz

from .events import collect_events


def to_ical_event(item):
    event = Event()
    event.add('uid', item.uid)
    event.add('summary', item.summary)
    event.add('dtstart', item.start)
    event.add('dtend', item.end)
    if item.recurrence:
        event.add('rrule', {
            'freq': 'weekly', 'byday': item.recurrence.byday, 'until': item.recurrence.until,
        })
        if item.recurrence.skipped:
            event.add('exdate', item.recurrence.skipped)
    if item.location:
        event.add('location', item.location)
    if item.description:
        event.add('description', item.description)
    event.add('dtstamp', timezone.now())
    return event


def build_calendar(user):
    cal = Calendar()
    cal.add('prodid', '-//Lineup//Lineup//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', 'Lineup')
    cal.add('x-wr-timezone', str(campus_tz()))
    for item in collect_events(user):
        cal.add_component(to_ical_event(item))
    # Adds the VTIMEZONE block describing America/Los_Angeles (incl. its DST rules),
    # which calendar apps need to interpret TZID=America/Los_Angeles correctly.
    cal.add_missing_timezones()
    return cal.to_ical()
