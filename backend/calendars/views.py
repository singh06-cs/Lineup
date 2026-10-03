from urllib.parse import quote

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from .builder import build_calendar
from .models import CalendarFeed


class FeedLinksView(APIView):
    """GET your feed links; POST to regenerate (revokes the old URL)."""

    def get(self, request):
        feed, _ = CalendarFeed.objects.get_or_create(user=request.user)
        return Response(self.links(request, feed))

    def post(self, request):
        feed, _ = CalendarFeed.objects.get_or_create(user=request.user)
        feed.regenerate()
        return Response(self.links(request, feed))

    def links(self, request, feed):
        url = request.build_absolute_uri(reverse('calendar-ics', args=[feed.token]))
        # webcal:// tells the OS "subscribe to this", rather than download it once.
        webcal = 'webcal://' + url.split('://', 1)[1]
        return {
            'feed_url': url,
            'webcal_url': webcal,
            'google_url': f'https://calendar.google.com/calendar/r?cid={quote(webcal, safe="")}',
        }


def ics_feed(request, token):
    """The feed itself: a plain Django view, no DRF auth. The token in the URL is the
    credential, because calendar servers fetching it can't log in."""
    feed = get_object_or_404(CalendarFeed.objects.select_related('user'), token=token)
    response = HttpResponse(build_calendar(feed.user), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'inline; filename="lineup.ics"'
    # Don't let shared caches (proxies) store someone's personal schedule.
    response['Cache-Control'] = 'private, max-age=300'
    return response

