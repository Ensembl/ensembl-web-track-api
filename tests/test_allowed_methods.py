#
#  See the NOTICE file distributed with this work for additional information
#  regarding copyright ownership.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Tests for ALLOWED_METHODS parsing and enforcement."""

from uuid import uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient

from tracks.models import Category, DatasetRelease, Source, Specifications, Track
from utils.helpers import parse_allowed_methods


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("get", ["get"]),
        (" GET ", ["get"]),
        ("get, POST, delete", ["delete", "get", "post"]),
        ("get,get,GET", ["get"]),
        ("\tPOST ,\n get ", ["get", "post"]),
        ("post", ["post"]),
        ("delete", ["delete"]),
    ],
)
def test_parse_allowed_methods(value, expected):
    """Test that parse_allowed_methods correctly parses valid configurations."""
    assert parse_allowed_methods(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        ",",
        "get,",
        ",get",
        "get,,post",
        "get, ,post",
        "get post",
        "typo",
        "get,typo",
        "*",
        "head",
        "options",
        "put",
        "patch",
        "trace",
        "get,options",
    ],
)
def test_parse_allowed_methods_rejects_invalid_configuration(value):
    """Test that parse_allowed_methods raises ImproperlyConfigured for invalid configurations."""
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_METHODS"):
        parse_allowed_methods(value)


@pytest.fixture
def api_client(settings):
    """Provide an APIClient with caching disabled for testing."""
    settings.ENABLE_CACHE = False
    return APIClient()


@pytest.fixture
def track_data(db):
    """Create a set of tracks, specifications, and sources for testing."""
    category = Category.objects.create(
        label="Test category",
        track_category_id="test-category",
        type="Genomic",
    )
    primary_spec = Specifications.objects.create(
        name="primary-spec",
        label="Primary specification",
        category=category,
        trigger=["track", "test"],
        type="regular",
        files=["main-file"],
        browser="GenomeBrowser",
    )
    additional_spec = Specifications.objects.create(
        name="additional-spec",
        label="Additional specification",
        category=category,
        trigger=["track", "test"],
        type="regular",
        files=["main-file"],
        browser="StructuralVariant",
    )
    source = Source.objects.create(
        name="Existing source",
        url="https://example.org/existing",
        details="Existing reference",
    )

    genome_id = uuid4()
    dataset_id = uuid4()

    def make_track(genome):
        track = Track.objects.create(
            genome_id=genome,
            dataset_id=dataset_id,
            datafiles={"main-file": "existing.bb"},
        )
        track.specifications.add(primary_spec)
        track.sources.add(source)
        return track

    track = make_track(genome_id)
    sibling = make_track(genome_id)
    unrelated = make_track(uuid4())

    DatasetRelease.objects.create(
        genome_id=genome_id,
        dataset_id=dataset_id,
        release_label="2026-01-01",
    )

    return {
        "track": track,
        "sibling": sibling,
        "unrelated": unrelated,
        "primary_spec": primary_spec,
        "additional_spec": additional_spec,
        "create_payload": {
            "genome_id": str(genome_id),
            "dataset_id": str(uuid4()),
            "datafiles": ["new.bb"],
            "track_types": [primary_spec.name],
            "sources": [
                {
                    "name": "New source",
                    "url": "https://example.org/new",
                    "details": "New reference",
                }
            ],
        },
        "link_payload": {
            "track_id": str(track.track_id),
            "type_name": additional_spec.name,
        },
    }


def database_snapshot():
    """Capture rows and relationships, rather than only row counts."""
    models = (
        Category,
        DatasetRelease,
        Source,
        Specifications,
        Track,
        Track.specifications.through,
        Track.sources.through,
    )
    return {
        model._meta.label: list(model.objects.order_by("pk").values())
        for model in models
    }


def endpoint_url(endpoint, data):
    """Return the URL for a given endpoint and track data."""
    return {
        "create": "/tracks/create",
        "link": "/tracks/link_type",
        "track": f"/track/{data['track'].track_id}",
        "genome": f"/track_categories/{data['track'].genome_id}",
    }[endpoint]


def send_write(client, endpoint, data):
    """Send a write request to the specified endpoint with the provided data."""
    url = endpoint_url(endpoint, data)
    if endpoint == "create":
        return client.post(url, data["create_payload"], format="json")
    if endpoint == "link":
        return client.post(url, data["link_payload"], format="json")
    return client.delete(url)


def allowed_header(response):
    """Extract the allowed methods from the response's Allow header."""
    return {method.strip() for method in response["Allow"].split(",") if method.strip()}


@pytest.mark.django_db
class TestAllowedMethods:
    @pytest.mark.parametrize("endpoint", ["create", "link", "track", "genome"])
    def test_read_only_rejects_writes_without_changes(
        self, settings, api_client, track_data, endpoint
    ):
        """Test that write requests are rejected when only GET is allowed."""
        settings.ALLOWED_METHODS = ["get"]
        before = database_snapshot()

        response = send_write(api_client, endpoint, track_data)

        assert response.status_code == 405
        assert database_snapshot() == before
        expected = {"GET"} if endpoint in {"track", "genome"} else set()
        assert allowed_header(response) == expected

    @pytest.mark.parametrize("endpoint", ["create", "link", "track", "genome"])
    @pytest.mark.parametrize("policy", ["all", "required_only"])
    def test_enabled_writes_reach_handlers(
        self, settings, api_client, track_data, endpoint, policy
    ):
        """Test that write requests succeed when allowed by the policy."""
        required = "post" if endpoint in {"create", "link"} else "delete"
        settings.ALLOWED_METHODS = (
            ["get", "post", "delete"] if policy == "all" else [required]
        )
        original_track_ids = set(Track.objects.values_list("pk", flat=True))
        original_source_count = Source.objects.count()

        response = send_write(api_client, endpoint, track_data)

        expected_status = {
            "create": 201,
            "link": 200,
            "track": 204,
            "genome": 204,
        }
        assert response.status_code == expected_status[endpoint]

        if endpoint == "create":
            created = Track.objects.get(track_id=response.data["track_id"])
            assert set(Track.objects.values_list("pk", flat=True)) == (
                original_track_ids | {created.pk}
            )
            assert created.datafiles == {"main-file": "new.bb"}
            assert list(created.specifications.all()) == [track_data["primary_spec"]]
            assert (
                list(created.sources.values("name", "url", "details"))
                == track_data["create_payload"]["sources"]
            )
            assert Source.objects.count() == original_source_count + 1

        elif endpoint == "link":
            assert set(
                track_data["track"].specifications.values_list("pk", flat=True)
            ) == {
                track_data["primary_spec"].pk,
                track_data["additional_spec"].pk,
            }
            assert set(Track.objects.values_list("pk", flat=True)) == (
                original_track_ids
            )

        else:
            deleted_ids = {track_data["track"].pk}
            if endpoint == "genome":
                deleted_ids.add(track_data["sibling"].pk)

            assert set(Track.objects.values_list("pk", flat=True)) == (
                original_track_ids - deleted_ids
            )
            assert not Track.specifications.through.objects.filter(
                track_id__in=deleted_ids
            ).exists()
            assert not Track.sources.through.objects.filter(
                track_id__in=deleted_ids
            ).exists()

    @pytest.mark.parametrize("methods", [["get"], ["get", "post", "delete"]])
    @pytest.mark.parametrize("endpoint", ["track", "genome"])
    def test_get_remains_available(
        self, settings, api_client, track_data, methods, endpoint
    ):
        """Test that GET requests are always allowed when configured."""
        settings.ALLOWED_METHODS = methods
        before = database_snapshot()

        response = api_client.get(endpoint_url(endpoint, track_data))

        assert response.status_code == 200
        assert database_snapshot() == before

    @pytest.mark.parametrize("endpoint", ["track", "genome"])
    def test_get_is_rejected_when_excluded(
        self, settings, api_client, track_data, endpoint
    ):
        """Test that GET requests are rejected when not included in ALLOWED_METHODS."""
        settings.ALLOWED_METHODS = ["post", "delete"]
        before = database_snapshot()

        response = api_client.get(endpoint_url(endpoint, track_data))

        assert response.status_code == 405
        assert allowed_header(response) == {"DELETE"}
        assert database_snapshot() == before

    @pytest.mark.parametrize(
        ("endpoint", "method", "expected_allow"),
        [
            ("track", "post", {"GET", "DELETE"}),
            ("genome", "post", {"GET", "DELETE"}),
            ("create", "delete", {"POST"}),
            ("link", "delete", {"POST"}),
            ("create", "get", {"POST"}),
            ("link", "get", {"POST"}),
        ],
    )
    def test_view_restrictions_are_preserved(
        self, settings, api_client, track_data, endpoint, method, expected_allow
    ):
        """Test that view restrictions are preserved when ALLOWED_METHODS is changed."""
        settings.ALLOWED_METHODS = ["get", "post", "delete"]
        before = database_snapshot()

        response = getattr(api_client, method)(endpoint_url(endpoint, track_data))

        assert response.status_code == 405
        assert allowed_header(response) == expected_allow
        assert database_snapshot() == before

    @pytest.mark.parametrize("methods", [["get"], ["get", "post", "delete"]])
    @pytest.mark.parametrize("endpoint", ["create", "link", "track", "genome"])
    @pytest.mark.parametrize("method", ["head", "options", "put", "patch", "trace"])
    def test_unsupported_methods(
        self, settings, api_client, track_data, methods, endpoint, method
    ):
        """Test that unsupported HTTP methods are rejected with 405."""
        settings.ALLOWED_METHODS = methods
        before = database_snapshot()

        response = api_client.generic(
            method.upper(), endpoint_url(endpoint, track_data)
        )

        assert response.status_code == 405
        supported = {"GET", "DELETE"} if endpoint in {"track", "genome"} else {"POST"}
        assert allowed_header(response) == (
            supported & {value.upper() for value in methods}
        )
        assert database_snapshot() == before

    def test_policy_changes_do_not_modify_shared_view_methods(
        self, settings, api_client, track_data
    ):
        """Test that changing ALLOWED_METHODS does not affect the shared view's http_method_names."""
        url = endpoint_url("track", track_data)
        before = database_snapshot()

        settings.ALLOWED_METHODS = ["get"]
        assert api_client.delete(url).status_code == 405

        settings.ALLOWED_METHODS = ["get", "post", "delete"]
        response = api_client.post(url)
        assert response.status_code == 405
        assert allowed_header(response) == {"GET", "DELETE"}

        settings.ALLOWED_METHODS = ["get"]
        response = api_client.delete(url)
        assert response.status_code == 405
        assert allowed_header(response) == {"GET"}
        assert database_snapshot() == before
