"""Redis response caching with a version derived from the SQLite files."""

import hashlib
import json
import logging
from functools import wraps
from inspect import signature
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from redis import ConnectionPool, Redis
from redis.exceptions import RedisError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

logger = logging.getLogger(__name__)

redis_pool = ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=settings.REDIS_MAX_CONNECTION,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)
redis_client = Redis(connection_pool=redis_pool)


_database_version = None
_version_initialized = False


def initialize_database_version():
    """Hash the immutable SQLite snapshot once at startup, using bounded memory.

    The database copy must finish before startup. Updates require app restart.
    If hashing fails, caching remains bypassed until the next restart.
    """
    global _database_version, _version_initialized
    if _version_initialized:
        return
    _version_initialized = True
    if not settings.ENABLE_CACHE:
        return
    try:
        digest = hashlib.sha256()
        with Path(settings.DATABASE_PATH).open('rb') as database:
            for chunk in iter(lambda: database.read(1024 * 1024), b''):
                digest.update(chunk)
        _database_version = digest.hexdigest()
    except OSError:
        logger.warning('Cannot hash database; bypassing cache until restart', exc_info=True)


def get_database_version():
    """Return the startup checksum without accessing the filesystem."""
    return _database_version


def _mark_cache_response(response, outcome, write_outcome=None):
    """Expose cache diagnostics without changing the response payload or status."""
    response['X-Track-Cache'] = outcome
    if write_outcome is not None:
        response['X-Track-Cache-Write'] = write_outcome
    return response


def redis_cache(key_prefix, *, params=(), ttl=None):
    """Cache 200 GET responses using route arguments and declared query defaults.

    Each (name, default) in params must match the view's parameter handling.
    Unknown query parameters are ignored. Use a distinct prefix per endpoint.
    """
    def decorator(func):
        handler_signature = signature(func)
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            if not settings.ENABLE_CACHE:
                return _mark_cache_response(func(self, request, *args, **kwargs), 'BYPASS')
            version = get_database_version()
            if version is None:
                return _mark_cache_response(func(self, request, *args, **kwargs), 'BYPASS')
            # Binding normalizes positional and keyword route arguments.
            bound = handler_signature.bind(self, request, *args, **kwargs)
            bound.apply_defaults()
            route_parts = [
                f"{name}={quote(str(value), safe='')}"
                for name, value in bound.arguments.items()
                if name not in ('self', 'request')
            ]
            query_parts = [
                f"{name}={quote(str(request.query_params.get(name, default)), safe='')}"
                for name, default in params
            ]
            key = ':'.join([key_prefix, version, *route_parts, *query_parts])
            cache_write_allowed = True
            outcome = 'MISS'
            write_outcome = None
            try:
                cached = redis_client.get(key)
                if cached is not None:
                    return _mark_cache_response(Response(json.loads(cached)), 'HIT')
            except RedisError:
                outcome = 'ERROR'
                cache_write_allowed = False
                logger.warning('Redis cache read failed; bypassing cache for this request', exc_info=True)
            except (ValueError, UnicodeError):
                outcome = 'ERROR'
                logger.warning('Invalid cached response; querying database', exc_info=True)

            response = func(self, request, *args, **kwargs)
            if cache_write_allowed and response.status_code == 200:
                try:
                    redis_client.setex(
                        key, settings.CACHE_TTL if ttl is None else ttl,
                        JSONRenderer().render(response.data),
                    )
                except (RedisError, TypeError, ValueError):
                    write_outcome = 'ERROR'
                    logger.warning('Redis cache write failed', exc_info=True)
                else:
                    write_outcome = 'OK'
            return _mark_cache_response(response, outcome, write_outcome)
        return wrapper
    return decorator
