from django.urls import path

from .views import (
    FeedLinksView,
    GoogleCalendarConnectView,
    GoogleCalendarSyncView,
    GoogleCalendarView,
    google_calendar_callback,
)

urlpatterns = [
    path('feed/', FeedLinksView.as_view(), name='calendar-feed-links'),
    path('google/', GoogleCalendarView.as_view(), name='google-calendar'),
    path('google/connect/', GoogleCalendarConnectView.as_view(), name='google-calendar-connect'),
    path('google/sync/', GoogleCalendarSyncView.as_view(), name='google-calendar-sync'),
    path('google/callback/', google_calendar_callback, name='google-calendar-callback'),
]
