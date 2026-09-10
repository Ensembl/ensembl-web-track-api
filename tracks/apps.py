from django.apps import AppConfig


class TracksConfig(AppConfig):
    name = "tracks"

    def ready(self):
        from utils.redis_cache import initialize_database_version

        initialize_database_version()
