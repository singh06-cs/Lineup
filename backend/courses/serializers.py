import re

from django.db import transaction
from rest_framework import serializers

from .models import WEEKDAY_LETTERS, Course, Holiday, Meeting, Section, Term


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ['date', 'name']


class TermSerializer(serializers.ModelSerializer):
    holidays = HolidaySerializer(many=True, read_only=True)

    class Meta:
        model = Term
        fields = [
            'id', 'name', 'instruction_begins', 'instruction_ends',
            'finals_begin', 'finals_end', 'holidays',
        ]


class CourseSerializer(serializers.ModelSerializer):
    # Declared explicitly so the model's strict validators don't reject "ecs" / "36a"
    # before validate_subject/validate_number get the chance to normalize them.
    subject = serializers.CharField(max_length=10)
    number = serializers.CharField(max_length=10)

    class Meta:
        model = Course
        fields = ['id', 'subject', 'number', 'title', 'units']
        read_only_fields = ['id']
        # Used nested inside a section, where an existing course is looked up rather
        # than rejected, so the "course already exists" validator must not run here.
        validators = []

    def validate_subject(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r'[A-Z]{2,4}', value):
            raise serializers.ValidationError('Use the subject code, e.g. ECS.')
        return value

    def validate_number(self, value):
        # Accept what students type: "36a" -> "036A", "20" -> "020".
        match = re.fullmatch(r'(\d{1,3})([A-Za-z]{0,2})', value.strip())
        if not match:
            raise serializers.ValidationError('Use the course number, e.g. 036A or 150.')
        digits, letters = match.groups()
        return digits.zfill(3) + letters.upper()


class DaysField(serializers.CharField):
    """Accepts "wfm" or "M W F" and stores the canonical ordered form "MWF"."""

    def to_internal_value(self, data):
        letters = set(super().to_internal_value(data).replace(' ', '').upper())
        ordered = ''.join(day for day in WEEKDAY_LETTERS if day in letters)
        if not ordered or len(ordered) != len(letters):
            raise serializers.ValidationError('Use day letters M T W R F S U (R = Thursday).')
        return ordered


class WeeklySlotSerializerMixin:
    """Shared validation for anything built on the WeeklySlot model."""

    def validate(self, attrs):
        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'end_time': 'It must end after it starts.'})
        return super().validate(attrs)


class MeetingSerializer(WeeklySlotSerializerMixin, serializers.ModelSerializer):
    days = DaysField(max_length=20)

    class Meta:
        model = Meeting
        fields = ['id', 'kind', 'days', 'start_time', 'end_time', 'location']
        read_only_fields = ['id']


class SectionSerializer(serializers.ModelSerializer):
    """Read and write a section with its course and meetings in ONE request.

    DRF doesn't save nested data on its own, so create()/update() handle it:
    the course is found or created by its code, and meetings are (re)created.
    """

    course = CourseSerializer()
    meetings = MeetingSerializer(many=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    # From annotate() in the view.
    enrolled_count = serializers.IntegerField(read_only=True)
    is_enrolled = serializers.BooleanField(read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            'id', 'term', 'term_name', 'course', 'crn', 'section_code', 'instructor',
            'final_exam_start', 'final_exam_end', 'meetings',
            'enrolled_count', 'is_enrolled', 'can_edit', 'created_by',
        ]
        read_only_fields = ['id']

    def to_representation(self, section):
        data = super().to_representation(section)
        # Calendar order: first weekday (M T W R F S U), then start time. So a Tue/Thu
        # lecture comes before a Friday discussion, regardless of meeting type.
        data['meetings'].sort(key=lambda m: (WEEKDAY_LETTERS.index(m['days'][0]), m['start_time']))
        return data

    def get_can_edit(self, section):
        user = self.context['request'].user
        return user.is_staff or section.created_by_id == user.id

    def validate(self, attrs):
        start = attrs.get('final_exam_start', getattr(self.instance, 'final_exam_start', None))
        end = attrs.get('final_exam_end', getattr(self.instance, 'final_exam_end', None))
        if (start is None) != (end is None):
            raise serializers.ValidationError('Give both a final exam start and end, or neither.')
        if start and end and end <= start:
            raise serializers.ValidationError({'final_exam_end': 'The final exam must end after it starts.'})
        return attrs

    def find_or_create_course(self, data):
        course, _ = Course.objects.get_or_create(
            subject=data['subject'], number=data['number'],
            defaults={'title': data['title'], 'units': data.get('units')},
        )
        return course

    def create(self, validated_data):
        course_data = validated_data.pop('course')
        meetings = validated_data.pop('meetings')
        # Course, section and meetings are saved together or not at all.
        with transaction.atomic():
            section = Section.objects.create(course=self.find_or_create_course(course_data), **validated_data)
            Meeting.objects.bulk_create(Meeting(section=section, **m) for m in meetings)
        return section

    def update(self, section, validated_data):
        course_data = validated_data.pop('course', None)
        meetings = validated_data.pop('meetings', None)
        with transaction.atomic():
            if course_data:
                section.course = self.find_or_create_course(course_data)
            for field, value in validated_data.items():
                setattr(section, field, value)
            section.save()
            # Sending meetings replaces the whole list; leaving them out keeps them.
            if meetings is not None:
                section.meetings.all().delete()
                Meeting.objects.bulk_create(Meeting(section=section, **m) for m in meetings)
        return section
