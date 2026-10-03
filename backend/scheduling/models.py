from django.conf import settings
from django.db import models
from django.db.models import F, Q

from courses.models import WeeklySlot


class Shift(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='shifts',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    # No stored "spots_left": it's derived (capacity - signups) and computed in queries.
    capacity = models.PositiveIntegerField()
    # SET_NULL: the shift belongs to the org, so it outlives its creator's account.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shifts',
    )
    volunteers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Signup',
        related_name='shifts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')),
                name='shift_end_after_start',
                violation_error_message='A shift must end after it starts.',
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1),
                name='shift_capacity_at_least_one',
                violation_error_message='A shift needs at least one spot.',
            ),
        ]
        # Most common query: upcoming shifts for one organization.
        indexes = [
            models.Index(fields=['organization', 'start_time']),
        ]

    def __str__(self):
        return f'{self.title} ({self.start_time:%Y-%m-%d %H:%M})'


class Signup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='signups',
    )
    shift = models.ForeignKey(
        Shift,
        on_delete=models.CASCADE,
        related_name='signups',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'shift'],
                name='unique_signup',
                violation_error_message='You are already signed up for this shift.',
            ),
        ]

    def __str__(self):
        return f'{self.user} -> {self.shift}'


class ClubMeeting(WeeklySlot):
    """An org's regular weekly meeting, repeating through a term (skipping holidays).

    Inherits days/start_time/end_time/location and their constraints from WeeklySlot,
    the same base the course catalog's class Meeting uses.
    """

    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='club_meetings',
    )
    term = models.ForeignKey('courses.Term', on_delete=models.PROTECT, related_name='club_meetings')
    title = models.CharField(max_length=200, default='General meeting')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(WeeklySlot.Meta):
        ordering = ['term__instruction_begins', 'start_time']

    def __str__(self):
        return f'{self.organization}: {self.title} ({self.days} {self.start_time:%H:%M})'
