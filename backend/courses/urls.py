from rest_framework.routers import DefaultRouter

from .views import CourseViewSet, SectionViewSet, TermViewSet

router = DefaultRouter()
router.register('terms', TermViewSet, basename='term')
router.register('courses', CourseViewSet, basename='course')
router.register('sections', SectionViewSet, basename='section')

urlpatterns = router.urls
