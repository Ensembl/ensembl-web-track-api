from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError, TimeoutError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request

from utils import redis_cache as cache


@pytest.fixture
def setup_cache(settings, tmp_path, monkeypatch):
    database = tmp_path / 'tracks.sqlite3'
    database.write_bytes(b'initial')
    settings.DATABASE_PATH = str(database)
    settings.ENABLE_CACHE = True
    cache.initialize_database_version()
    client = Mock()
    client.get.return_value = None
    monkeypatch.setattr(cache, 'redis_client', client)
    return database, client


def test_startup_checksum_is_reused(setup_cache, monkeypatch):
    import hashlib
    from pathlib import Path

    assert cache.get_database_version() == hashlib.sha256(b'initial').hexdigest()
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', Mock(side_effect=AssertionError('must not read again')))
        cache.initialize_database_version()
        for _ in range(3):
            assert cache.get_database_version() == hashlib.sha256(b'initial').hexdigest()


def test_identical_copies_have_same_checksum(setup_cache, settings, tmp_path, monkeypatch):
    first = cache.get_database_version()
    copy = tmp_path / 'another.sqlite3'
    copy.write_bytes(b'initial')
    settings.DATABASE_PATH = str(copy)
    monkeypatch.setattr(cache, '_version_initialized', False)
    cache.initialize_database_version()
    assert cache.get_database_version() == first


def test_cache_hit_and_key_isolation(setup_cache, settings):
    settings.CACHE_TTL = 86400
    _, client = setup_cache
    handler = Mock(return_value=Response({'track_categories': []}))
    wrapped = cache.redis_cache('track_category', params=(('browser', 'GenomeBrowser'), ('release', '')))(handler)
    request = Request(APIRequestFactory().get('/'))
    wrapped(None, request, 'genome1')
    assert client.setex.call_args.args[1] == 86400
    first = client.get.call_args.args[0]
    client.get.return_value = '{"track_categories": []}'
    assert wrapped(None, request, 'genome1').data == {'track_categories': []}
    assert handler.call_count == 1
    wrapped(None, request, 'genome2')
    assert client.get.call_args.args[0] != first
    assert first.endswith(':browser=GenomeBrowser:release=')


def test_disabled_bypasses_stat_and_redis(setup_cache, settings, monkeypatch):
    _, client = setup_cache
    settings.ENABLE_CACHE = False
    version = Mock(side_effect=AssertionError('must not stat'))
    monkeypatch.setattr(cache, 'get_database_version', version)
    handler = Mock(return_value=Response({}))
    cache.redis_cache('track_category')(handler)(None, Request(APIRequestFactory().get('/')), 'genome')
    client.get.assert_not_called()
    handler.assert_called_once()


@pytest.mark.parametrize('error', [ConnectionError, TimeoutError])
def test_redis_read_failure_skips_write(setup_cache, error):
    _, client = setup_cache
    client.get.side_effect = error('offline')
    handler = Mock(return_value=Response({'fresh': True}))
    response = cache.redis_cache('track_category')(handler)(
        None, Request(APIRequestFactory().get('/')), 'genome'
    )
    assert response.status_code == 200
    assert response.data == {'fresh': True}
    handler.assert_called_once()
    client.get.assert_called_once()
    client.setex.assert_not_called()


def test_redis_write_failure_preserves_response(setup_cache):
    _, client = setup_cache
    client.setex.side_effect = ConnectionError('offline')
    handler = Mock(return_value=Response({'fresh': True}))
    response = cache.redis_cache('track_category')(handler)(
        None, Request(APIRequestFactory().get('/')), 'genome'
    )
    assert response.data == {'fresh': True}
    handler.assert_called_once()
    client.setex.assert_called_once()


def test_query_defaults_and_route_binding(setup_cache):
    _, client = setup_cache

    @cache.redis_cache('track_category', params=(('browser', 'GenomeBrowser'), ('release', '')))
    def handler(self, request, genome_id):
        return Response({})

    def key(query='', **kwargs):
        request = Request(APIRequestFactory().get('/' + query))
        handler(None, request, **kwargs)
        return client.get.call_args.args[0]

    baseline = key(genome_id='one')
    assert key('?browser=GenomeBrowser', genome_id='one') == baseline
    assert key('?release=', genome_id='one') == baseline
    assert key('?unknown=value', genome_id='one') == baseline
    assert key('?browser=StructuralVariant', genome_id='one') != baseline
    assert key('?release=2026-09-01', genome_id='one') != baseline
    assert key('?browser=', genome_id='one') != baseline
    handler(None, Request(APIRequestFactory().get('/')), 'one')
    assert client.get.call_args.args[0] == baseline


@pytest.fixture
def stateful_cache(settings, tmp_path):
    database = tmp_path / 'database.sqlite3'
    database.write_bytes(b'initial')
    settings.DATABASE_PATH = str(database)
    settings.ENABLE_CACHE = True
    cache.initialize_database_version()
    settings.CACHE_TTL = 86400
    return database


def test_changed_database_uses_new_key_after_restart(stateful_cache, monkeypatch):
    calls = []

    @cache.redis_cache('test')
    def handler(self, request):
        calls.append(True)
        return Response({'generation': len(calls)})

    request = Request(APIRequestFactory().get('/'))
    assert handler(None, request).data == {'generation': 1}
    stateful_cache.write_bytes(b'new deployment')
    # Version remains fixed for the lifetime of the running app.
    assert handler(None, request).data == {'generation': 1}
    monkeypatch.setattr(cache, '_version_initialized', False)
    cache.initialize_database_version()
    assert handler(None, request).data == {'generation': 2}


@pytest.mark.parametrize('code', [400, 404, 500])
def test_error_responses_are_not_cached(stateful_cache, isolated_redis, code):
    handler = Mock(return_value=Response({'error': 'failure'}, status=code))
    wrapped = cache.redis_cache('test')(handler)
    for _ in range(2):
        assert wrapped(None, Request(APIRequestFactory().get('/'))).status_code == code
    assert handler.call_count == 2
    isolated_redis.setex.assert_not_called()


def test_missing_database_at_startup_bypasses_cache(stateful_cache, isolated_redis, monkeypatch):
    stateful_cache.unlink()
    monkeypatch.setattr(cache, '_database_version', None)
    monkeypatch.setattr(cache, '_version_initialized', False)
    cache.initialize_database_version()
    handler = Mock(return_value=Response({}))
    cache.redis_cache('test')(handler)(None, Request(APIRequestFactory().get('/')))
    handler.assert_called_once()
    isolated_redis.get.assert_not_called()
    isolated_redis.setex.assert_not_called()


def test_corrupt_entry_is_replaced(stateful_cache, isolated_redis):
    isolated_redis.get.side_effect = None
    isolated_redis.get.return_value = 'not JSON'
    handler = Mock(return_value=Response({'valid': True}))
    response = cache.redis_cache('test')(handler)(None, Request(APIRequestFactory().get('/')))
    assert response.data == {'valid': True}
    handler.assert_called_once()
    isolated_redis.setex.assert_called_once()


def test_explicit_ttl_override(stateful_cache, isolated_redis):
    handler = Mock(return_value=Response({}))
    cache.redis_cache('test', ttl=60)(handler)(None, Request(APIRequestFactory().get('/')))
    assert isolated_redis.setex.call_args.args[1] == 60


def test_handler_exception_is_not_retried(stateful_cache, isolated_redis):
    handler = Mock(side_effect=RuntimeError('handler failure'))
    with pytest.raises(RuntimeError, match='handler failure'):
        cache.redis_cache('test')(handler)(None, Request(APIRequestFactory().get('/')))
    handler.assert_called_once()
    isolated_redis.setex.assert_not_called()


@pytest.fixture
def cached_track(db, stateful_cache):
    import uuid
    from tracks.models import Category, DatasetRelease, Specifications, Track

    genome_id, dataset_id = uuid.uuid4(), uuid.uuid4()
    category = Category.objects.create(label='Genomic', track_category_id='genomic')
    track = Track.objects.create(genome_id=genome_id, dataset_id=dataset_id)
    DatasetRelease.objects.create(genome_id=genome_id, dataset_id=dataset_id, release_label='2026-01-01')
    for browser in ('GenomeBrowser', 'StructuralVariant'):
        spec = Specifications.objects.create(
            name=browser, label=browser, browser=browser, category=category, type='regular',
        )
        track.specifications.add(spec)
    return track


@pytest.mark.parametrize('endpoint', ['track_categories', 'track'])
def test_endpoint_hits_skip_database(cached_track, endpoint, django_assert_num_queries):
    from rest_framework.test import APIClient

    client = APIClient()
    identifier = cached_track.genome_id if endpoint == 'track_categories' else cached_track.track_id
    url = f'/{endpoint}/{identifier}'
    first = client.get(url)
    assert first.status_code == 200
    with django_assert_num_queries(0):
        for suffix in ('', '?browser=GenomeBrowser', '?ignored=value'):
            assert client.get(url + suffix).data == first.data
    sv = client.get(url + '?browser=StructuralVariant')
    assert sv.status_code == 200
    assert sv.data != first.data
    with django_assert_num_queries(0):
        assert client.get(url + '?browser=StructuralVariant').data == sv.data


def test_release_cache_isolation(cached_track, django_assert_num_queries):
    from rest_framework.test import APIClient

    client = APIClient()
    url = f'/track_categories/{cached_track.genome_id}'
    latest = client.get(url)
    with django_assert_num_queries(0):
        assert client.get(url + '?release=').data == latest.data
    assert client.get(url + '?release=2025-01-01').status_code == 404
    assert client.get(url + '?release=2026-01-01').data == latest.data
    with django_assert_num_queries(0):
        assert client.get(url + '?release=2026-01-01').data == latest.data


def test_track_cache_separates_track_ids(cached_track, django_assert_num_queries):
    from rest_framework.test import APIClient
    from tracks.models import Track

    other = Track.objects.create(
        genome_id=cached_track.genome_id,
        dataset_id=cached_track.dataset_id,
        datafiles={'signal': 'other.bw'},
    )
    other.specifications.set(cached_track.specifications.all())
    client = APIClient()
    responses = {}
    for track in (cached_track, other):
        url = f'/track/{track.track_id}'
        response = client.get(url)
        assert response.status_code == 200
        assert response.data['track_id'] == str(track.track_id)
        assert response.data['datafiles'] == track.datafiles
        responses[url] = response.data
    with django_assert_num_queries(0):
        for url, expected in responses.items():
            assert client.get(url).data == expected


def test_track_cache_preserves_detail_fields(cached_track, django_assert_num_queries):
    from rest_framework.test import APIClient

    cached_track.datafiles = {'signal': 'signal.bw'}
    cached_track.save()
    spec = cached_track.specifications.get(browser='GenomeBrowser')
    spec.settings = {'height': 100}
    spec.description = 'Not included in the single-track response'
    spec.additional_info = 'Extra information'
    spec.save()
    client = APIClient()
    url = f'/track/{cached_track.track_id}'
    first = client.get(url)
    assert first.status_code == 200
    assert first.data['datafiles'] == {'signal': 'signal.bw'}
    assert first.data['settings'] == {'height': 100}
    assert 'description' not in first.data
    assert 'additional_info' not in first.data
    with django_assert_num_queries(0):
        assert client.get(url).data == first.data


@pytest.mark.parametrize('browser', ['', 'invalid'])
def test_track_invalid_browser_not_cached(cached_track, isolated_redis, browser):
    from rest_framework.test import APIClient

    client = APIClient()
    url = f'/track/{cached_track.track_id}?browser={browser}'
    for _ in range(2):
        assert client.get(url).status_code == 400
    isolated_redis.setex.assert_not_called()


def test_track_missing_id_not_cached(cached_track, isolated_redis):
    import uuid
    from rest_framework.test import APIClient

    client = APIClient()
    for _ in range(2):
        response = client.get(f'/track/{uuid.UUID(int=0)}')
        assert response.status_code == 404
        assert response.data == {'error': 'No track found with this track id.'}
    isolated_redis.setex.assert_not_called()


def test_track_missing_browser_configuration_not_cached(cached_track, isolated_redis):
    from rest_framework.test import APIClient

    spec = cached_track.specifications.get(browser='StructuralVariant')
    cached_track.specifications.remove(spec)
    client = APIClient()
    url = f'/track/{cached_track.track_id}?browser=StructuralVariant'
    for _ in range(2):
        assert client.get(url).status_code == 404
    isolated_redis.setex.assert_not_called()
    # A previously missing configuration must become available immediately.
    cached_track.specifications.add(spec)
    assert client.get(url).status_code == 200
    isolated_redis.setex.assert_called_once()


def test_track_ignores_release_parameter(cached_track, django_assert_num_queries):
    from rest_framework.test import APIClient

    client = APIClient()
    url = f'/track/{cached_track.track_id}'
    first = client.get(url)
    assert first.status_code == 200
    with django_assert_num_queries(0):
        assert client.get(url + '?release=2020-01-01').data == first.data
