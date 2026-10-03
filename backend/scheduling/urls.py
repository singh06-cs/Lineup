from rest_framework.routers import DefaultRouter

from .views import ClubMeetingViewSet, ShiftViewSet

router = DefaultRouter()
router.register('shifts', ShiftViewSet, basename='shift')
router.register('club-meetings', ClubMeetingViewSet, basename='club-meeting')

urlpatterns = router.urls
