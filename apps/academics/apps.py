from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    name = "apps.academics"
    label = "academics"

    def ready(self) -> None:
        from apps.accounts.services import register_scope_resolver

        from .services import containing_scopes

        register_scope_resolver(containing_scopes)
