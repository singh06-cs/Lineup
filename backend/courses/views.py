from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.response import Response

from .filters import SectionFilter
from .models import Course, Meeting, Section, Term
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
        return (
            Section.objects
            .select_related('course', 'term', 'created_by')
            # One extra query for ALL sections' meetings, not one per section.
            .prefetch_related(Prefetch('meetings', queryset=Meeting.objects.order_by('kind', 'start_time')))
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
