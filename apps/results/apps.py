from django.apps import AppConfig


class ResultsConfig(AppConfig):
    name = "apps.results"
    label = "results"

    def ready(self) -> None:
        from . import signals  # noqa: F401
