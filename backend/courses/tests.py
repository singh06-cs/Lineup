from datetime import date, datetime, time
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import Course, Holiday, Meeting, Section, Term


def make_term(name='Fall 2026', begins=date(2026, 9, 23), ends=date(2026, 12, 4)):
    return Term.objects.create(name=name, instruction_begins=begins, instruction_ends=ends)


class CatalogConstraintTests(TestCase):
    def setUp(self):
        self.term = make_term()
        self.course = Course.objects.create(subject='ECS', number='036A', title='Programming in Python')
        self.section = Section.objects.create(term=self.term, course=self.course, crn='12345')

    def assert_db_rejects(self, create):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create()

    def test_crn_unique_within_a_term(self):
        self.assert_db_rejects(
            lambda: Section.objects.create(term=self.term, course=self.course, crn='12345'),
        )

    def test_same_crn_allowed_in_a_different_term(self):
        winter = make_term('Winter 2027', date(2027, 1, 4), date(2027, 3, 12))

        Section.objects.create(term=winter, course=self.course, crn='12345')

        self.assertEqual(Section.objects.filter(crn='12345').count(), 2)

    def test_course_code_unique(self):
        self.assert_db_rejects(
            lambda: Course.objects.create(subject='ECS', number='036A', title='Duplicate'),
        )

    def test_meeting_must_end_after_start(self):
        self.assert_db_rejects(lambda: Meeting.objects.create(
            section=self.section, days='MWF', start_time=time(11), end_time=time(10),
        ))

    def test_meeting_days_must_be_valid_and_in_order(self):
        for bad in ['', 'FWM', 'MX', 'Thu']:
            with self.subTest(days=bad):
                self.assert_db_rejects(lambda bad=bad: Meeting.objects.create(
                    section=self.section, days=bad, start_time=time(10), end_time=time(11),
                ))

    def test_friendly_validation_messages(self):
        meeting = Meeting(section=self.section, days='TR', start_time=time(12), end_time=time(11))
        with self.assertRaises(ValidationError) as ctx:
            meeting.full_clean()
        self.assertIn('A meeting must end after it starts.', ctx.exception.messages)

        with self.assertRaises(ValidationError) as ctx:
            Section(term=self.term, course=self.course, crn='12a45').full_clean()
        self.assertIn('crn', ctx.exception.message_dict)

    def test_final_exam_must_end_after_start(self):
        start = timezone.make_aware(datetime(2026, 12, 8, 10))
        self.section.final_exam_start = start
        self.section.final_exam_end = start
        self.assert_db_rejects(self.section.save)

    def test_term_with_sections_cannot_be_deleted(self):
        # PROTECT: deleting a term must not silently wipe out students' schedules.
        with self.assertRaises(ProtectedError):
            self.term.delete()

    def test_weekdays(self):
        meeting = Meeting(section=self.section, days='MWF', start_time=time(10), end_time=time(11))
        self.assertEqual(meeting.weekdays, [0, 2, 4])
        meeting.days = 'TR'
        self.assertEqual(meeting.weekdays, [1, 3])


class LoadTermsCommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command('load_terms', *args, stdout=out)
        return out.getvalue()

    def test_loads_official_2026_27_quarters(self):
        self.run_command()

        fall = Term.objects.get(name='Fall 2026')
        self.assertEqual(fall.instruction_begins, date(2026, 9, 23))
        self.assertEqual(fall.instruction_ends, date(2026, 12, 4))
        self.assertEqual(
            list(fall.holidays.values_list('date', flat=True)),
            [date(2026, 11, 11), date(2026, 11, 26), date(2026, 11, 27)],
        )
        self.assertEqual(
            list(Term.objects.values_list('name', flat=True)),
            ['Fall 2026', 'Winter 2027', 'Spring 2027'],
        )

    def test_running_twice_does_not_duplicate(self):
        self.run_command()
        output = self.run_command()

        self.assertEqual(Term.objects.count(), 3)
        self.assertEqual(Holiday.objects.count(), 6)
        self.assertIn('Updated Fall 2026', output)

    def test_rerun_corrects_stale_holidays(self):
        self.run_command('--term', 'Fall 2026')
        fall = Term.objects.get(name='Fall 2026')
        Holiday.objects.create(term=fall, date=date(2026, 10, 1), name='Typo holiday')

        self.run_command('--term', 'Fall 2026')

        self.assertFalse(fall.holidays.filter(name='Typo holiday').exists())

    def test_single_term_and_unknown_term(self):
        self.run_command('--term', 'Winter 2027')
        self.assertEqual(list(Term.objects.values_list('name', flat=True)), ['Winter 2027'])

        with self.assertRaises(CommandError):
            self.run_command('--term', 'Fall 1999')
