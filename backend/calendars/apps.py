from django.apps import AppConfig


class CalendarsConfig(AppConfig):
    name = 'calendars'

    def ready(self):
        from . import signals  # noqa: F401  (registers the receivers)
