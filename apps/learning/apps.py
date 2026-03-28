from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = "apps.learning"

    def ready(self):
        import apps.learning.signals  # noqa
