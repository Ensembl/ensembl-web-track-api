from django.core.exceptions import ImproperlyConfigured
import re

def parse_cache_ttl(value):
    """Convert seconds or a duration such as 30m, 24h or 1d to Redis seconds."""
    match = re.fullmatch(r"([0-9]+)([smhd]?)", value.strip().lower())
    if not match or int(match[1]) <= 0:
        raise ImproperlyConfigured(
            "CACHE_TTL must be a positive integer in seconds or a duration such as 24h."
        )
    return int(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]
