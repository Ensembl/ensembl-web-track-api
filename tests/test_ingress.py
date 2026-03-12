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

"""
Unit tests for Track API ingress endpoints.
Tests CreateTrack and LinkTypeToTrack views.
"""

import pytest
import uuid
from rest_framework.test import APIClient
from rest_framework import status
from tracks.models import Track, Specifications, Category


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Return DRF API client for making requests."""
    return APIClient()


@pytest.fixture
def category():
    """Create a test category."""
    return Category.objects.create(
        label="Test Category",
        track_category_id="test-category",
        type="Genomic"
    )


@pytest.fixture
def specification_two_files(category):
    """Create a specification with two file slots."""
    return Specifications.objects.create(
        name="test-spec-two-files",
        label="Test Spec Two Files",
        category=category,
        trigger=["track", "test"],
        type="regular",
        files=["detail-file", "summary-file"],
        browser="GenomeBrowser"
    )


@pytest.fixture
def specification_one_file(category):
    """Create a specification with one file slot."""
    return Specifications.objects.create(
        name="test-spec-one-file",
        label="Test Spec One File",
        category=category,
        trigger=["track", "test"],
        type="regular",
        files=["main-file"],
        browser="GenomeBrowser"
    )


@pytest.fixture
def specification_matching_files(category):
    """Create another specification with same files as specification_two_files."""
    return Specifications.objects.create(
        name="test-spec-matching",
        label="Test Spec Matching",
        category=category,
        trigger=["track", "test2"],
        type="regular",
        files=["detail-file", "summary-file"],  # Same as specification_two_files
        browser="StructuralVariant"
    )


@pytest.fixture
def specification_different_files(category):
    """Create a specification with different files."""
    return Specifications.objects.create(
        name="test-spec-different",
        label="Test Spec Different",
        category=category,
        trigger=["track", "test3"],
        type="regular",
        files=["other-file", "another-file"],
        browser="GenomeBrowser"
    )


@pytest.fixture
def sample_track(specification_two_files):
    """Create a sample track linked to specification_two_files."""
    track = Track.objects.create(
        dataset_id=uuid.uuid4(),
        genome_id=uuid.uuid4(),
        datafiles={"detail-file": "test.bb", "summary-file": "test.bw"}
    )
    track.specifications.add(specification_two_files)
    return track


# ── CreateTrack Tests ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCreateTrack:
    """Tests for POST /tracks/create endpoint."""

    def test_create_track_with_one_datafile(self, api_client, specification_two_files):
        """Test creating a track with one datafile fills second slot with empty string."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb"],
            "track_types": ["test-spec-two-files"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert "track_id" in response.data

        # Verify track was created
        track = Track.objects.get(track_id=response.data["track_id"])
        assert track.datafiles == {"detail-file": "file1.bb", "summary-file": ""}
        assert track.specifications.count() == 1
        assert track.specifications.first() == specification_two_files

    def test_create_track_with_two_datafiles(self, api_client, specification_two_files):
        """Test creating a track with two datafiles."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb", "file2.bw"],
            "track_types": ["test-spec-two-files"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_201_CREATED

        track = Track.objects.get(track_id=response.data["track_id"])
        assert track.datafiles == {"detail-file": "file1.bb", "summary-file": "file2.bw"}

    def test_create_track_with_multiple_types(
            self, api_client, specification_two_files, specification_matching_files
    ):
        """Test creating a track with multiple track types."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb", "file2.bw"],
            "track_types": ["test-spec-two-files", "test-spec-matching"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_201_CREATED

        track = Track.objects.get(track_id=response.data["track_id"])
        assert track.specifications.count() == 2
        type_names = set(track.specifications.values_list('name', flat=True))
        assert type_names == {"test-spec-two-files", "test-spec-matching"}

    def test_create_track_invalid_uuid_dataset(self, api_client):
        """Test that invalid dataset_id UUID is rejected."""
        data = {
            "dataset_id": "not-a-uuid",
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb"],
            "track_types": ["test-spec"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "dataset_id" in response.data["details"]

    def test_create_track_invalid_uuid_genome(self, api_client):
        """Test that invalid genome_id UUID is rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": "not-a-uuid",
            "datafiles": ["file1.bb"],
            "track_types": ["test-spec"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "genome_id" in response.data["details"]

    def test_create_track_no_datafiles(self, api_client, specification_two_files):
        """Test that empty datafiles list is rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": [],
            "track_types": ["test-spec-two-files"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "datafiles" in response.data["details"]

    def test_create_track_too_many_datafiles(self, api_client, specification_two_files):
        """Test that more than 2 datafiles is rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb", "file2.bw", "file3.txt"],
            "track_types": ["test-spec-two-files"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "datafiles" in response.data["details"]

    def test_create_track_nonexistent_type(self, api_client):
        """Test that nonexistent track type is rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb"],
            "track_types": ["nonexistent-type"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "track_types" in response.data["details"]
        assert "not found" in str(response.data["details"]["track_types"])

    def test_create_track_mismatched_files(
            self, api_client, specification_two_files, specification_different_files
    ):
        """Test that track types with different file lists are rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            "genome_id": str(uuid.uuid4()),
            "datafiles": ["file1.bb", "file2.bw"],
            "track_types": ["test-spec-two-files", "test-spec-different"]
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "track_types" in response.data["details"]
        assert "same files list" in str(response.data["details"]["track_types"])

    def test_create_track_missing_required_fields(self, api_client):
        """Test that missing required fields are rejected."""
        data = {
            "dataset_id": str(uuid.uuid4()),
            # Missing genome_id, datafiles, track_types
        }

        response = api_client.post('/tracks/create', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "genome_id" in response.data["details"]
        assert "datafiles" in response.data["details"]
        assert "track_types" in response.data["details"]


# ── LinkTypeToTrack Tests ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLinkTypeToTrack:
    """Tests for POST /tracks/link_type endpoint."""

    def test_link_type_success(self, api_client, sample_track, specification_matching_files):
        """Test successfully linking a new type to an existing track."""
        data = {
            "track_id": str(sample_track.track_id),
            "type_name": "test-spec-matching"
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["track_id"] == str(sample_track.track_id)
        assert "successfully" in response.data["message"]

        # Verify link was created
        sample_track.refresh_from_db()
        assert sample_track.specifications.count() == 2
        type_names = set(sample_track.specifications.values_list('name', flat=True))
        assert "test-spec-matching" in type_names

    def test_link_type_track_not_found(self, api_client):
        """Test that linking to nonexistent track fails."""
        data = {
            "track_id": str(uuid.uuid4()),
            "type_name": "test-spec"
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "track_id" in response.data["details"]
        assert "not found" in str(response.data["details"]["track_id"])

    def test_link_type_type_not_found(self, api_client, sample_track):
        """Test that linking nonexistent type fails."""
        data = {
            "track_id": str(sample_track.track_id),
            "type_name": "nonexistent-type"
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_name" in response.data["details"]
        assert "not found" in str(response.data["details"]["type_name"])

    def test_link_type_already_linked(self, api_client, sample_track, specification_two_files):
        """Test that linking already-linked type fails."""
        data = {
            "track_id": str(sample_track.track_id),
            "type_name": "test-spec-two-files"  # Already linked in fixture
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_name" in response.data["details"]
        assert "already linked" in str(response.data["details"]["type_name"])

    def test_link_type_files_mismatch(self, api_client, sample_track, specification_different_files):
        """Test that linking type with different files fails."""
        data = {
            "track_id": str(sample_track.track_id),
            "type_name": "test-spec-different"
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_name" in response.data["details"]
        assert "do not match" in str(response.data["details"]["type_name"])

    def test_link_type_invalid_track_uuid(self, api_client):
        """Test that invalid track UUID is rejected."""
        data = {
            "track_id": "not-a-uuid",
            "type_name": "test-spec"
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "track_id" in response.data["details"]

    def test_link_type_missing_fields(self, api_client):
        """Test that missing required fields are rejected."""
        data = {
            "track_id": str(uuid.uuid4())
            # Missing type_name
        }

        response = api_client.post('/tracks/link_type', data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_name" in response.data["details"]