from django.db.models import Count, Exists, OuterRef
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .filters import SectionFilter
from .models import Course, Enrollment, Section, Term
from .permissions import IsCreatorOrStaff
from .serializers import CourseSerializer, SectionSerializer, TermSerializer


class TermViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Term.objects.prefetch_related('holidays')
    serializer_class = TermSerializer
    pagination_class = None  # a handful of quarters; the frontend wants them all


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    """Search the catalog's courses. New courses arrive via POST /api/sections/."""

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['subject', 'number', 'title']


class SectionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SectionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = SectionFilter
    # "ECS 36" works: SearchFilter splits on spaces and every word must match some field.
    search_fields = ['course__subject', 'course__number', 'course__title', 'crn', 'instructor']

    def get_queryset(self):
        user = self.request.user
        return (
            Section.objects
            .select_related('course', 'term', 'created_by')
            # One extra query for ALL sections' meetings, not one per section.
            .prefetch_related('meetings')
            .annotate(
                enrolled_count=Count('enrollments'),
                is_enrolled=Exists(Enrollment.objects.filter(section=OuterRef('pk'), user=user)),
            )
            # Explicit: Django drops Meta.ordering from GROUP BY (Count) queries, and
            # pagination over an unordered queryset can repeat or skip rows.
            .order_by('course__subject', 'course__number', 'section_code', 'pk')
        )

    def get_permissions(self):
        if self.action in {'update', 'partial_update', 'destroy'}:
            return [permissions.IsAuthenticated(), IsCreatorOrStaff()]
        return [permissions.IsAuthenticated()]

    def respond_with_section(self, section, status_code=status.HTTP_200_OK):
        section = self.get_queryset().get(pk=section.pk)
        return Response(self.get_serializer(section).data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = serializer.save(created_by=request.user)
        return self.respond_with_section(section, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return self.respond_with_section(serializer.save())

    def perform_destroy(self, section):
        # Don't let one student delete a section other students have on their schedules.
        if section.enrollments.exclude(user=self.request.user).exists():
            raise serializers.ValidationError(
                {'detail': 'Other students have this section on their schedule, so it cannot be deleted.'}
            )
        section.delete()

    @action(detail=True, methods=['post', 'delete'])
    def enroll(self, request, pk=None):
        """POST adds this section to your schedule, DELETE drops it."""
        section = self.get_object()
        if request.method == 'POST':
            services.enroll(request.user, section)
            return self.respond_with_section(section, status.HTTP_201_CREATED)
        services.drop(request.user, section)
        return self.respond_with_section(section)
