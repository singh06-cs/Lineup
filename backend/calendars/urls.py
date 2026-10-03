from django.urls import path

from .views import FeedLinksView

urlpatterns = [
    path('feed/', FeedLinksView.as_view(), name='calendar-feed-links'),
]
