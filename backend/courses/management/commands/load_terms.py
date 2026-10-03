"""python manage.py load_terms

Loads official UC Davis quarter dates and holidays into the catalog. Safe to run
again: existing terms are updated in place, never duplicated.

Source: UC Davis Office of the University Registrar, Academic Calendar 2026-2027
https://registrar.ucdavis.edu/calendar/academic-calendar
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from courses.models import Holiday, Term

TERMS = {
    'Fall 2026': {
        'instruction_begins': date(2026, 9, 23),
        'instruction_ends': date(2026, 12, 4),
        'finals_begin': date(2026, 12, 7),
        'finals_end': date(2026, 12, 11),
        'holidays': [
            (date(2026, 11, 11), 'Veterans Day'),
            (date(2026, 11, 26), 'Thanksgiving'),
            (date(2026, 11, 27), 'Thanksgiving'),
        ],
    },
    'Winter 2027': {
        'instruction_begins': date(2027, 1, 4),
        'instruction_ends': date(2027, 3, 12),
        'finals_begin': date(2027, 3, 15),
        'finals_end': date(2027, 3, 19),
        'holidays': [
            (date(2027, 1, 18), 'Martin Luther King, Jr. Day'),
            (date(2027, 2, 15), "Presidents' Day"),
        ],
    },
    'Spring 2027': {
        'instruction_begins': date(2027, 3, 29),
        'instruction_ends': date(2027, 6, 3),
        # Spring finals are Fri 6/4 and Mon-Thu 6/7-10 (the weekend has no exams).
        'finals_begin': date(2027, 6, 4),
        'finals_end': date(2027, 6, 10),
        'holidays': [
            (date(2027, 5, 31), 'Memorial Day'),
        ],
    },
}


class Command(BaseCommand):
    help = 'Load official UC Davis quarter dates and holidays (2026-2027).'

    def add_arguments(self, parser):
        parser.add_argument('--term', help='Only load one term, e.g. "Fall 2026".')

    def handle(self, *args, **options):
        names = [options['term']] if options['term'] else list(TERMS)
        unknown = [name for name in names if name not in TERMS]
        if unknown:
            raise CommandError(f'Unknown term {unknown[0]!r}. Choose from: {", ".join(TERMS)}')

        for name in names:
            data = dict(TERMS[name])
            holidays = data.pop('holidays')
            # One transaction per term: a term is never left half-loaded.
            with transaction.atomic():
                term, created = Term.objects.update_or_create(name=name, defaults=data)
                # Replace holidays wholesale so a corrected calendar removes stale dates too.
                term.holidays.all().delete()
                Holiday.objects.bulk_create(
                    Holiday(term=term, date=day, name=label) for day, label in holidays
                )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f'{verb} {name}: {term.instruction_begins} to {term.instruction_ends}, '
                f'{len(holidays)} holiday(s)'
            ))
