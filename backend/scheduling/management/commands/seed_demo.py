"""python manage.py seed_demo

Fills a development or opted-in demo database with sample data so the app can be shown
off without typing everything in: two users, two orgs, shifts in the coming week,
weekly club meetings, and a few course sections with one student enrolled.

Re-running replaces demo data unless --if-empty is passed. Refuses to run unless
DEBUG or DEMO_MODE is on, so normal production data stays protected.

Everything here is fictional: org names end in "(demo)", and demo sections use
section codes D01..D05, "Demo instructor", and made-up CRNs starting with 9.
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from courses.models import Course, Enrollment, Meeting, Section, Term
from courses.services import campus_tz
from organizations.models import Membership, Organization
from scheduling.models import ClubMeeting, Shift, Signup

User = get_user_model()

DEMO_PASSWORD = 'Lineup-demo-2026'  # public, shared demo accounts
DEMO_INSTRUCTOR = 'Demo instructor'

COURSES = [
    # subject, number, title, units, crn, code, meetings [(kind, days, start, end, location)]
    ('ECS', '036A', 'Programming in Python', 4, '90001', 'D01', [
        ('LEC', 'MWF', time(10, 0), time(10, 50), 'Wellman 2'),
        ('DIS', 'R', time(14, 10), time(15, 0), 'Olson 6'),
    ]),
    ('MAT', '021A', 'Calculus', 4, '90002', 'D02', [
        ('LEC', 'TR', time(12, 10), time(13, 30), 'Young 198'),
        ('DIS', 'W', time(16, 10), time(17, 0), 'Wellman 115'),
    ]),
    ('ENL', '003', 'Introduction to Literature', 4, '90003', 'D03', [
        ('LEC', 'TR', time(9, 0), time(10, 20), 'Olson 158'),
    ]),
    ('PHY', '007A', 'General Physics', 4, '90004', 'D04', [
        ('LEC', 'MWF', time(10, 0), time(10, 50), 'Roessler 66'),  # clashes with ECS 036A
    ]),
    ('STA', '013', 'Elementary Statistics', 4, '90005', 'D05', [
        ('LEC', 'MWF', time(13, 10), time(14, 0), 'Giedt 1001'),
    ]),
]


def next_weekday(weekday):
    """The next date (after today, campus time) that falls on `weekday` (Monday=0)."""
    today = timezone.now().astimezone(campus_tz()).date()
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), campus_tz())


class Command(BaseCommand):
    help = 'Load fictional accounts and schedules in development or an opted-in demo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--if-empty', action='store_true',
            help='Seed only a new database; preserve existing accounts and application data.',
        )

    def handle(self, *args, **options):
        if not (settings.DEBUG or settings.DEMO_MODE):
            raise CommandError('seed_demo requires DEBUG=True or an explicit DEMO_MODE=True.')

        call_command('load_terms', stdout=self.stdout)
        term = Term.objects.filter(
            instruction_ends__gte=timezone.now().astimezone(campus_tz()).date(),
        ).first()

        with transaction.atomic():
            if options['if_empty'] and (
                User.objects.exists() or Organization.objects.exists() or Section.objects.exists()
            ):
                self.stdout.write('Existing application data found; skipping demo seed.')
                return
            self.clear()
            admin, student = self.create_users()
            pantry, coding = self.create_orgs(admin, student)
            self.create_club_meetings(term, pantry, coding)
            self.create_courses(term, student)
            self.create_shifts(admin, student, pantry, coding)

        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready. Log in as demo_admin or demo_student (password: see '
            f'DEMO_PASSWORD in {__file__.split("backend/")[-1]}).'
        ))

    def clear(self):
        Organization.objects.filter(name__endswith='(demo)').delete()
        Section.objects.filter(instructor=DEMO_INSTRUCTOR).delete()
        User.objects.filter(username__in=['demo_admin', 'demo_student']).delete()

    def create_users(self):
        admin = User.objects.create_user(
            'demo_admin', 'demo_admin@example.com', DEMO_PASSWORD, first_name='Avery',
        )
        student = User.objects.create_user(
            'demo_student', 'demo_student@example.com', DEMO_PASSWORD, first_name='Sam',
        )
        return admin, student

    def create_orgs(self, admin, student):
        pantry = Organization.objects.create(
            name='Aggie Food Pantry Volunteers (demo)',
            description='Restocking, sorting and front-desk shifts at the campus pantry.',
        )
        coding = Organization.objects.create(
            name='Davis Coding Club (demo)',
            description='Weekly workshops and tabling for the coding club.',
        )
        for org in (pantry, coding):
            Membership.objects.create(user=admin, organization=org, role=Membership.Role.ADMIN)
            Membership.objects.create(user=student, organization=org)
        return pantry, coding

    def create_club_meetings(self, term, pantry, coding):
        if term is None:
            return
        ClubMeeting.objects.create(
            organization=coding, term=term, title='Weekly workshop',
            days='T', start_time=time(18), end_time=time(19), location='Kemper 1131',
        )
        ClubMeeting.objects.create(
            organization=pantry, term=term, title='Volunteer briefing',
            days='R', start_time=time(19), end_time=time(19, 30), location='Freeborn Hall',
        )

    def create_courses(self, term, student):
        if term is None:
            self.stdout.write(self.style.WARNING('No current or upcoming term; skipping courses.'))
            return
        for subject, number, title, units, crn, code, meetings in COURSES:
            course, _ = Course.objects.get_or_create(
                subject=subject, number=number, defaults={'title': title, 'units': units},
            )
            section = Section.objects.create(
                term=term, course=course, crn=crn, section_code=code, instructor=DEMO_INSTRUCTOR,
            )
            Meeting.objects.bulk_create(
                Meeting(section=section, kind=kind, days=days, start_time=start, end_time=end, location=where)
                for kind, days, start, end, where in meetings
            )
            if crn in ('90001', '90002'):  # the student's current schedule
                Enrollment.objects.create(user=student, section=section)

    def create_shifts(self, admin, student, pantry, coding):
        monday, tuesday, wednesday = next_weekday(0), next_weekday(1), next_weekday(2)
        friday, saturday = next_weekday(4), next_weekday(5)
        shifts = [
            # org, title, start, end, capacity, location, signed up
            (pantry, 'Pantry restock', at(monday, 10), at(monday, 12), 4, 'Pantry back room', []),
            (pantry, 'Front desk', at(tuesday, 15), at(tuesday, 17), 2, 'Pantry entrance', [admin]),
            (pantry, 'Evening sort', at(wednesday, 18), at(wednesday, 20), 3, 'Pantry', [student]),
            (coding, 'Tabling at the MU', at(friday, 12), at(friday, 14), 1, 'Memorial Union', [admin]),
            (pantry, "Farmers market pickup", at(saturday, 9), at(saturday, 12), 6, 'Central Park', []),
        ]
        for org, title, start, end, capacity, location, people in shifts:
            shift = Shift.objects.create(
                organization=org, title=title, start_time=start, end_time=end,
                capacity=capacity, location=location, created_by=admin,
            )
            Signup.objects.bulk_create(Signup(user=u, shift=shift) for u in people)
