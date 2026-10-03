from django.db.models import Count, Exists, F, OuterRef
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from organizations.models import Membership

from . import services
from .filters import ShiftFilter
from .models import ClubMeeting, Shift, Signup
from .permissions import IsOrgAdminOfObject
from .serializers import ClubMeetingSerializer, RosterEntrySerializer, ShiftSerializer


class ShiftViewSet(viewsets.ModelViewSet):
    serializer_class = ShiftSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ShiftFilter
    search_fields = ['title', 'location', 'description']
    ordering_fields = ['start_time', 'spots_left']
    ordering = ['start_time']
    admin_actions = {'update', 'partial_update', 'destroy', 'roster'}

    def get_queryset(self):
        user = self.request.user
        my_memberships = Membership.objects.filter(user=user)
        signup_count = Count('signups')
        # Everything the list needs comes back in ONE query, however many shifts there are:
        # select_related JOINs the org, and annotate() computes the rest in SQL.
        return (
            Shift.objects
            .filter(organization_id__in=my_memberships.values('organization_id'))
            .select_related('organization', 'created_by')
            .annotate(
                signup_count=signup_count,
                spots_left=F('capacity') - signup_count,
                is_signed_up=Exists(Signup.objects.filter(shift=OuterRef('pk'), user=user)),
                can_manage=Exists(my_memberships.filter(
                    organization=OuterRef('organization'), role=Membership.Role.ADMIN,
                )),
            )
        )

    def get_permissions(self):
        if self.action in self.admin_actions:
            return [permissions.IsAuthenticated(), IsOrgAdminOfObject()]
        return [permissions.IsAuthenticated()]

    def respond_with_shift(self, shift, status_code=status.HTTP_200_OK):
        # Re-read through get_queryset() so the response has fresh annotated fields.
        shift = self.get_queryset().get(pk=shift.pk)
        return Response(self.get_serializer(shift).data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = serializer.save(created_by=request.user)
        return self.respond_with_shift(shift, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        shift = serializer.save()
        return self.respond_with_shift(shift)

    @action(detail=True, methods=['post', 'delete'])
    def signup(self, request, pk=None):
        """POST to sign up for this shift, DELETE to cancel."""
        shift = self.get_object()
        if request.method == 'POST':
            services.sign_up(request.user, shift)
            return self.respond_with_shift(shift, status.HTTP_201_CREATED)
        services.cancel_signup(request.user, shift)
        return self.respond_with_shift(shift)

    @action(detail=False, methods=['get'], url_path='class-conflicts')
    def class_conflicts(self, request):
        """Your upcoming shifts that now clash with your class schedule."""
        results = services.shifts_conflicting_with_classes(request.user)
        shifts = {s.pk: s for s in self.get_queryset().filter(pk__in=[r['shift'].pk for r in results])}
        return Response([
            {'shift': self.get_serializer(shifts[r['shift'].pk]).data, 'conflicts': r['conflicts']}
            for r in results
        ])

    @action(detail=True, methods=['get'])
    def roster(self, request, pk=None):
        shift = self.get_object()
        signups = shift.signups.select_related('user').order_by('created_at')
        return Response(RosterEntrySerializer(signups, many=True).data)


class ClubMeetingViewSet(viewsets.ModelViewSet):
    """GET /api/club-meetings/?organization=3&term=1 — weekly meetings of your orgs."""

    serializer_class = ClubMeetingSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['organization', 'term']
    pagination_class = None  # a few per org

    def get_queryset(self):
        my_memberships = Membership.objects.filter(user=self.request.user)
        return (
            ClubMeeting.objects
            .filter(organization_id__in=my_memberships.values('organization_id'))
            .select_related('organization', 'term')
            .annotate(can_manage=Exists(my_memberships.filter(
                organization=OuterRef('organization'), role=Membership.Role.ADMIN,
            )))
            .order_by('term__instruction_begins', 'start_time', 'pk')
        )

    def get_permissions(self):
        if self.action in {'update', 'partial_update', 'destroy'}:
            return [permissions.IsAuthenticated(), IsOrgAdminOfObject()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.save()
        return Response(
            self.get_serializer(self.get_queryset().get(pk=meeting.pk)).data,
            status=status.HTTP_201_CREATED,
        )
