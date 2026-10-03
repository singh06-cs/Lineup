import django_filters
from django.utils import timezone

from .models import Shift


class ShiftFilter(django_filters.FilterSet):
    """Query params for GET /api/shifts/, e.g. ?organization=3&upcoming=true&available=true"""

    organization = django_filters.NumberFilter(field_name='organization_id')
    starts_after = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='gte')
    starts_before = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='lte')
    upcoming = django_filters.BooleanFilter(method='filter_upcoming')
    available = django_filters.BooleanFilter(method='filter_available')
    mine = django_filters.BooleanFilter(method='filter_mine')

    class Meta:
        model = Shift
        fields = []

    def filter_upcoming(self, queryset, name, value):
        now = timezone.now()
        return queryset.filter(end_time__gt=now) if value else queryset.filter(end_time__lte=now)

    # These two filter on annotations, so they rely on the view's get_queryset().
    def filter_available(self, queryset, name, value):
        return queryset.filter(spots_left__gt=0) if value else queryset.filter(spots_left__lte=0)

    def filter_mine(self, queryset, name, value):
        return queryset.filter(is_signed_up=value)
