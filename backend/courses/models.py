"""Shared UC Davis course catalog.

Two kinds of time live here, and keeping them apart matters:
- Term and holiday DATES (DateField): calendar days, no time zone.
- Meeting TIMES (TimeField): wall-clock times on campus ("10:00 in Davis"), stored
  without a zone and interpreted in settings.CAMPUS_TIME_ZONE. A class at 10:00 stays
  at 10:00 local across the daylight-saving change in November; a stored UTC instant
  would drift by an hour.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

# UC Davis writes weekdays as M T W R F (R = Thursday, so it isn't confused with Tuesday).
WEEKDAY_LETTERS = 'MTWRFSU'
DAYS_PATTERN = r'^M?T?W?R?F?S?U?$'


class Term(models.Model):
    name = models.CharField(max_length=30, unique=True, help_text='e.g. "Fall 2026"')
    instruction_begins = models.DateField()
    instruction_ends = models.DateField()
    finals_begin = models.DateField(null=True, blank=True)
    finals_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['instruction_begins']
        constraints = [
            models.CheckConstraint(
                condition=Q(instruction_ends__gte=F('instruction_begins')),
                name='term_instruction_ends_after_begins',
                violation_error_message='Instruction must end on or after the day it begins.',
            ),
            models.CheckConstraint(
                condition=Q(finals_end__gte=F('finals_begin')),
                name='term_finals_end_after_begin',
                violation_error_message='Finals must end on or after the day they begin.',
            ),
        ]

    def __str__(self):
        return self.name


class Holiday(models.Model):
    """A day with no classes during a term (classes on this date are skipped)."""

    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='holidays')
    date = models.DateField()
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['term', 'date'], name='unique_holiday_per_term_date'),
        ]

    def __str__(self):
        return f'{self.name} ({self.date})'


class Course(models.Model):
    subject = models.CharField(
        max_length=4,
        validators=[RegexValidator(r'^[A-Z]{2,4}$', 'Use the subject code in capitals, e.g. ECS.')],
    )
    number = models.CharField(
        max_length=5,
        validators=[RegexValidator(r'^\d{3}[A-Z]{0,2}$', 'Use the 3-digit number, e.g. 036A or 150.')],
    )
    title = models.CharField(max_length=200)
    units = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ['subject', 'number']
        constraints = [
            models.UniqueConstraint(
                fields=['subject', 'number'],
                name='unique_course_code',
                violation_error_message='This course is already in the catalog.',
            ),
        ]

    def __str__(self):
        return f'{self.subject} {self.number}'


class Section(models.Model):
    # PROTECT, not CASCADE: students' schedules point at sections, so deleting a term
    # or course by mistake must fail loudly instead of silently wiping schedules.
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name='sections')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='sections')
    crn = models.CharField(
        'CRN',
        max_length=5,
        validators=[RegexValidator(r'^\d{5}$', 'A CRN is 5 digits.')],
    )
    section_code = models.CharField(max_length=4, blank=True, help_text='e.g. "A01"')
    instructor = models.CharField(max_length=100, blank=True)
    final_exam_start = models.DateTimeField(null=True, blank=True)
    final_exam_end = models.DateTimeField(null=True, blank=True)
    # Shared catalog: anyone can add a missing section; we record who did.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sections',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['course__subject', 'course__number', 'section_code']
        constraints = [
            # CRNs are reused across quarters, so they're only unique within a term.
            models.UniqueConstraint(
                fields=['term', 'crn'],
                name='unique_crn_per_term',
                violation_error_message='A section with this CRN already exists for this term.',
            ),
            models.CheckConstraint(
                condition=Q(final_exam_end__gt=F('final_exam_start')),
                name='section_final_ends_after_start',
                violation_error_message='The final exam must end after it starts.',
            ),
        ]

    def __str__(self):
        code = f' {self.section_code}' if self.section_code else ''
        return f'{self.course}{code} ({self.term}, CRN {self.crn})'


class Meeting(models.Model):
    """One weekly time slot of a section, e.g. the lecture or the discussion."""

    class Kind(models.TextChoices):
        LECTURE = 'LEC', 'Lecture'
        DISCUSSION = 'DIS', 'Discussion'
        LAB = 'LAB', 'Lab'
        SEMINAR = 'SEM', 'Seminar'
        OTHER = 'OTH', 'Other'

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='meetings')
    kind = models.CharField(max_length=3, choices=Kind.choices, default=Kind.LECTURE)
    days = models.CharField(
        max_length=7,
        validators=[RegexValidator(DAYS_PATTERN, 'Use days in order from MTWRFSU, e.g. "MWF" or "TR".')],
        help_text='Days in order using M T W R F S U (R = Thursday), e.g. "MWF".',
    )
    start_time = models.TimeField(help_text='Campus local time')
    end_time = models.TimeField(help_text='Campus local time')
    location = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['section', 'kind', 'start_time']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')),
                name='meeting_ends_after_start',
                violation_error_message='A meeting must end after it starts.',
            ),
            # Same rule as the validator, enforced by the database too ("" is rejected).
            models.CheckConstraint(
                condition=Q(days__regex=DAYS_PATTERN) & ~Q(days=''),
                name='meeting_days_valid',
                violation_error_message='Use days in order from MTWRFSU, e.g. "MWF" or "TR".',
            ),
        ]

    @property
    def weekdays(self):
        """Python weekday numbers (Monday=0) for this meeting, e.g. "MWF" -> [0, 2, 4]."""
        return [WEEKDAY_LETTERS.index(letter) for letter in self.days]

    def __str__(self):
        return f'{self.section.course} {self.get_kind_display()} {self.days} {self.start_time:%H:%M}'
