import django_filters

from .models import Section


class SectionFilter(django_filters.FilterSet):
    """GET /api/sections/?term=1&subject=ECS&mine=true"""

    term = django_filters.NumberFilter(field_name='term_id')
    subject = django_filters.CharFilter(field_name='course__subject', lookup_expr='iexact')
    number = django_filters.CharFilter(field_name='course__number', lookup_expr='iexact')
    crn = django_filters.CharFilter(field_name='crn')
    mine = django_filters.BooleanFilter(field_name='is_enrolled')  # annotation from the view

    class Meta:
        model = Section
        fields = []
