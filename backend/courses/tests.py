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
        self.assertIn('It must end after it starts.', ctx.exception.messages)

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


# ---------- Phase 13: catalog API ----------

from django.contrib.auth import get_user_model  # noqa: E402
from rest_framework import status  # noqa: E402
from rest_framework.test import APITestCase  # noqa: E402

from .models import Enrollment  # noqa: E402
from .services import class_conflicts  # noqa: E402

User = get_user_model()

SECTIONS = '/api/sections/'


def section_payload(term, crn='12345', subject='ECS', number='036A', meetings=None, **extra):
    payload = {
        'term': term.pk,
        'course': {'subject': subject, 'number': number, 'title': 'Programming in Python', 'units': '4.0'},
        'crn': crn,
        'section_code': 'A01',
        'instructor': 'Lee',
        'meetings': meetings if meetings is not None else [
            {'kind': 'LEC', 'days': 'MWF', 'start_time': '10:00', 'end_time': '10:50', 'location': 'Wellman 2'},
            {'kind': 'DIS', 'days': 'R', 'start_time': '14:10', 'end_time': '15:00', 'location': 'Olson 6'},
        ],
    }
    payload.update(extra)
    return payload


class CatalogApiTestCase(APITestCase):
    def setUp(self):
        self.term = make_term()
        self.alice = User.objects.create_user('alice', 'alice@example.com', 'pw-for-tests-1')
        self.bob = User.objects.create_user('bob', 'bob@example.com', 'pw-for-tests-1')
        self.client.force_authenticate(self.alice)

    def add_section(self, **kwargs):
        response = self.client.post(SECTIONS, section_payload(self.term, **kwargs), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data


class CatalogApiTests(CatalogApiTestCase):
    def test_add_section_with_course_and_meetings_in_one_request(self):
        data = self.add_section()

        self.assertEqual(data['course']['subject'], 'ECS')
        self.assertEqual(len(data['meetings']), 2)
        self.assertEqual(data['created_by'], 'alice')
        self.assertTrue(data['can_edit'])
        self.assertEqual(Course.objects.count(), 1)

    def test_existing_course_is_reused_not_duplicated(self):
        self.add_section(crn='12345')
        self.add_section(crn='12346')

        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Section.objects.count(), 2)

    def test_input_is_normalized(self):
        data = self.add_section(subject='ecs', number='36a', meetings=[
            {'kind': 'LEC', 'days': 'f w m', 'start_time': '10:00', 'end_time': '10:50'},
        ])

        self.assertEqual((data['course']['subject'], data['course']['number']), ('ECS', '036A'))
        self.assertEqual(data['meetings'][0]['days'], 'MWF')

    def test_duplicate_crn_in_term_rejected(self):
        self.add_section(crn='12345')

        response = self.client.post(SECTIONS, section_payload(self.term, crn='12345'), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_meeting_rejected_and_nothing_saved(self):
        response = self.client.post(SECTIONS, section_payload(self.term, meetings=[
            {'kind': 'LEC', 'days': 'MWF', 'start_time': '11:00', 'end_time': '10:00'},
        ]), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Course.objects.count(), 0)  # validation runs before anything is written

    def test_search_and_filters(self):
        self.add_section(crn='11111', subject='ECS', number='036A')
        self.add_section(crn='22222', subject='MAT', number='021A')

        def crns(query):
            return [s['crn'] for s in self.client.get(f'{SECTIONS}{query}').data['results']]

        self.assertEqual(crns('?search=ECS 36'), ['11111'])
        self.assertEqual(crns('?subject=mat'), ['22222'])
        self.assertEqual(crns('?crn=11111'), ['11111'])
        self.assertEqual(crns(f'?term={self.term.pk}'), ['11111', '22222'])

    def test_list_query_count_is_constant(self):
        for i in range(10):
            self.add_section(crn=f'1{i:04d}')

        # count + sections (with course/term JOINed) + one prefetch for all meetings
        with self.assertNumQueries(3):
            self.client.get(SECTIONS)

    def test_only_creator_can_edit(self):
        section_id = self.add_section()['id']
        self.client.force_authenticate(self.bob)

        response = self.client.patch(f'{SECTIONS}{section_id}/', {'instructor': 'Hacker'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editing_meetings_replaces_them(self):
        section_id = self.add_section()['id']

        response = self.client.patch(f'{SECTIONS}{section_id}/', {'meetings': [
            {'kind': 'LEC', 'days': 'TR', 'start_time': '09:00', 'end_time': '10:20'},
        ]}, format='json')

        self.assertEqual([m['days'] for m in response.data['meetings']], ['TR'])

    def test_cannot_delete_section_others_are_enrolled_in(self):
        section_id = self.add_section()['id']
        Enrollment.objects.create(user=self.bob, section_id=section_id)

        response = self.client.delete(f'{SECTIONS}{section_id}/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Section.objects.filter(pk=section_id).exists())

    def test_terms_endpoint_includes_holidays(self):
        Holiday.objects.create(term=self.term, date=date(2026, 11, 11), name='Veterans Day')

        response = self.client.get('/api/terms/')

        self.assertEqual(response.data[0]['holidays'], [{'date': '2026-11-11', 'name': 'Veterans Day'}])


# ---------- Phase 14: enrolling and class-vs-class conflicts ----------

class EnrollmentTests(CatalogApiTestCase):
    def enroll(self, section_id):
        return self.client.post(f'{SECTIONS}{section_id}/enroll/')

    def test_enroll_and_drop(self):
        section_id = self.add_section()['id']

        enrolled = self.enroll(section_id)
        self.assertEqual(enrolled.status_code, status.HTTP_201_CREATED)
        self.assertTrue(enrolled.data['is_enrolled'])
        self.assertEqual(enrolled.data['enrolled_count'], 1)

        mine = self.client.get(f'{SECTIONS}?mine=true').data['results']
        self.assertEqual([s['id'] for s in mine], [section_id])

        dropped = self.client.delete(f'{SECTIONS}{section_id}/enroll/')
        self.assertFalse(dropped.data['is_enrolled'])

    def test_cannot_enroll_twice(self):
        section_id = self.add_section()['id']
        self.enroll(section_id)

        self.assertEqual(self.enroll(section_id).status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_one_section_per_course(self):
        first = self.add_section(crn='11111')['id']
        second = self.add_section(crn='22222', section_code='A02', meetings=[
            {'kind': 'LEC', 'days': 'TR', 'start_time': '16:10', 'end_time': '17:30'},
        ])['id']
        self.enroll(first)

        response = self.enroll(second)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Drop it first', str(response.data['detail']))

    def test_time_conflict_blocks_enrollment(self):
        ecs = self.add_section(crn='11111')['id']  # MWF 10:00-10:50
        mat = self.add_section(crn='22222', subject='MAT', number='021A', meetings=[
            {'kind': 'LEC', 'days': 'WF', 'start_time': '10:30', 'end_time': '11:20'},
        ])['id']
        self.enroll(ecs)

        response = self.enroll(mat)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ECS 036A Lecture', str(response.data['detail']))

    def test_back_to_back_and_different_days_are_fine(self):
        ecs = self.add_section(crn='11111')['id']  # MWF 10:00-10:50, R 14:10-15:00
        mat = self.add_section(crn='22222', subject='MAT', number='021A', meetings=[
            {'kind': 'LEC', 'days': 'MWF', 'start_time': '10:50', 'end_time': '11:40'},
            {'kind': 'DIS', 'days': 'T', 'start_time': '14:10', 'end_time': '15:00'},
        ])['id']
        self.enroll(ecs)

        self.assertEqual(self.enroll(mat).status_code, status.HTTP_201_CREATED)

    def test_different_terms_never_conflict(self):
        winter = make_term('Winter 2027', date(2027, 1, 4), date(2027, 3, 12))
        fall_ecs = self.add_section(crn='11111')['id']
        winter_mat = self.client.post(SECTIONS, section_payload(
            winter, crn='22222', subject='MAT', number='021A',
        ), format='json').data['id']
        self.enroll(fall_ecs)

        self.assertEqual(self.enroll(winter_mat).status_code, status.HTTP_201_CREATED)


# ---------- Phase 15: shifts vs classes (time zones!) ----------

class ClassConflictTests(CatalogApiTestCase):
    """Fall 2026 class: MWF 10:00-10:50 Pacific. Daylight saving ends Sun Nov 1, 2026."""

    def setUp(self):
        super().setUp()
        Holiday.objects.create(term=self.term, date=date(2026, 11, 11), name='Veterans Day')
        Enrollment.objects.create(user=self.alice, section_id=self.add_section()['id'])

    def utc(self, *args):
        return datetime(*args, tzinfo=timezone.UTC)

    def conflicts(self, start, end):
        return class_conflicts(self.alice, start, end)

    def test_conflict_before_dst_change(self):
        # Mon Oct 26, 10:00 PDT = 17:00 UTC
        self.assertTrue(self.conflicts(self.utc(2026, 10, 26, 17, 0), self.utc(2026, 10, 26, 17, 30)))
        self.assertFalse(self.conflicts(self.utc(2026, 10, 26, 18, 0), self.utc(2026, 10, 26, 18, 30)))

    def test_conflict_after_dst_change(self):
        # Mon Nov 2, 10:00 PST = 18:00 UTC. The class didn't move on the wall clock,
        # so in UTC it moved an hour later. Storing class times as UTC would get this wrong.
        self.assertFalse(self.conflicts(self.utc(2026, 11, 2, 17, 0), self.utc(2026, 11, 2, 17, 30)))
        self.assertTrue(self.conflicts(self.utc(2026, 11, 2, 18, 0), self.utc(2026, 11, 2, 18, 30)))

    def test_no_conflict_on_holidays_off_days_or_outside_term(self):
        holiday = self.conflicts(self.utc(2026, 11, 11, 18, 0), self.utc(2026, 11, 11, 19, 0))
        tuesday = self.conflicts(self.utc(2026, 11, 3, 18, 0), self.utc(2026, 11, 3, 19, 0))
        after_term = self.conflicts(self.utc(2026, 12, 7, 18, 0), self.utc(2026, 12, 7, 19, 0))

        self.assertEqual((holiday, tuesday, after_term), ([], [], []))

    def test_final_exam_conflict(self):
        section = Section.objects.get()
        section.final_exam_start = self.utc(2026, 12, 8, 16)
        section.final_exam_end = self.utc(2026, 12, 8, 18)
        section.save()

        self.assertEqual(
            self.conflicts(self.utc(2026, 12, 8, 17), self.utc(2026, 12, 8, 19)),
            ['ECS 036A final exam'],
        )


class MeetingOrderTests(CatalogApiTestCase):
    def test_meetings_listed_in_calendar_order(self):
        data = self.add_section(meetings=[
            {'kind': 'DIS', 'days': 'F', 'start_time': '15:10', 'end_time': '16:00'},
            {'kind': 'LEC', 'days': 'TR', 'start_time': '16:10', 'end_time': '17:30'},
            {'kind': 'LAB', 'days': 'T', 'start_time': '08:00', 'end_time': '10:50'},
        ])

        self.assertEqual(
            [(m['days'], m['start_time']) for m in data['meetings']],
            [('T', '08:00:00'), ('TR', '16:10:00'), ('F', '15:10:00')],
        )
