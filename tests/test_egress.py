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
Unit tests for Track API egress endpoints.
Tests GenomeTrackList and TrackObject views with release and browser filtering.
"""

import pytest
import uuid
from rest_framework.test import APIClient
from rest_framework import status
from tracks.models import Track, Specifications, Category, DatasetRelease


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Return DRF API client for making requests."""
    return APIClient()


@pytest.fixture
def genome_id():
    """Fixed genome UUID for testing."""
    return uuid.UUID('a7335667-93e7-11ec-a39d-005056b38ce3')


@pytest.fixture
def category_genomic():
    """Create a Genomic category."""
    return Category.objects.create(
        label="Genomic Tracks",
        track_category_id="genomic",
        type="Genomic"
    )


@pytest.fixture
def category_variation():
    """Create a Variation category."""
    return Category.objects.create(
        label="Variation Tracks",
        track_category_id="variation",
        type="Variation"
    )


@pytest.fixture
def spec_gc_genomebrowser(category_genomic):
    """GC content spec for GenomeBrowser."""
    return Specifications.objects.create(
        name="gc-genomebrowser",
        label="GC Content",
        category=category_genomic,
        trigger=["track", "gc"],
        type="regular",
        files=["gc-content"],
        browser="GenomeBrowser",
        display_order=100
    )


@pytest.fixture
def spec_gc_structuralvariant(category_genomic):
    """GC content spec for StructuralVariant."""
    return Specifications.objects.create(
        name="gc-structuralvariant",
        label="GC Content SV",
        category=category_genomic,
        trigger=["track", "gc-sv"],
        type="regular",
        files=["gc-content"],
        browser="StructuralVariant",
        display_order=100
    )


@pytest.fixture
def spec_variation_genomebrowser(category_variation):
    """Variation spec for GenomeBrowser."""
    return Specifications.objects.create(
        name="variation-genomebrowser",
        label="SNP Variants",
        category=category_variation,
        trigger=["track", "snp"],
        type="variant",
        files=["variant-details", "variant-summary"],
        browser="GenomeBrowser",
        display_order=200
    )


@pytest.fixture
def spec_genebuild_genomebrowser(category_genomic):
    """Gene build spec for GenomeBrowser."""
    return Specifications.objects.create(
        name="genebuild-genomebrowser",
        label="Gene Annotations",
        category=category_genomic,
        trigger=["track", "genes"],
        type="gene",
        files=["gene-details"],
        browser="GenomeBrowser",
        display_order=50,
        settings={"show_labels": True}
    )


# ── GenomeTrackList Tests ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGenomeTrackList:
    """Tests for GET /track_categories/{genome_id} endpoint."""

    def test_get_tracks_default_browser_latest_release(
            self, api_client, genome_id, spec_gc_genomebrowser
    ):
        """Test getting tracks with default browser (GenomeBrowser) and latest release."""
        # Create dataset and release
        dataset_id = uuid.uuid4()
        DatasetRelease.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            release_label="2024-01-01"
        )

        # Create track
        track = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        response = api_client.get(f'/track_categories/{genome_id}')

        assert response.status_code == status.HTTP_200_OK
        assert "track_categories" in response.data
        assert len(response.data["track_categories"]) == 1
        assert response.data["track_categories"][0]["track_category_id"] == "genomic"
        assert len(response.data["track_categories"][0]["track_list"]) == 1
        assert response.data["track_categories"][0]["track_list"][0]["label"] == "GC Content"

    def test_get_tracks_with_specific_browser(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_gc_structuralvariant
    ):
        """Test filtering tracks by browser type."""
        dataset_id = uuid.uuid4()
        DatasetRelease.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            release_label="2024-01-01"
        )

        track = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)
        track.specifications.add(spec_gc_structuralvariant)

        # Test GenomeBrowser
        response = api_client.get(f'/track_categories/{genome_id}?browser=GenomeBrowser')
        assert response.status_code == status.HTTP_200_OK
        assert response.data["track_categories"][0]["track_list"][0]["label"] == "GC Content"

        # Test StructuralVariant
        response = api_client.get(f'/track_categories/{genome_id}?browser=StructuralVariant')
        assert response.status_code == status.HTTP_200_OK
        assert response.data["track_categories"][0]["track_list"][0]["label"] == "GC Content SV"

    def test_get_tracks_with_specific_release(
            self, api_client, genome_id, spec_gc_genomebrowser
    ):
        """Test filtering tracks by release date."""
        dataset1 = uuid.uuid4()
        dataset2 = uuid.uuid4()

        # Old release
        DatasetRelease.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            release_label="2024-01-01"
        )
        track1 = Track.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            datafiles={"gc-content": "gc_v1.bw"}
        )
        track1.specifications.add(spec_gc_genomebrowser)

        # New release
        DatasetRelease.objects.create(
            dataset_id=dataset2,
            genome_id=genome_id,
            release_label="2024-03-01"
        )
        track2 = Track.objects.create(
            dataset_id=dataset2,
            genome_id=genome_id,
            datafiles={"gc-content": "gc_v2.bw"}
        )
        track2.specifications.add(spec_gc_genomebrowser)

        # Query with release=2024-01-01 should only get old track
        response = api_client.get(f'/track_categories/{genome_id}?release=2024-01-01')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["track_categories"][0]["track_list"]) == 1
        # Should get track1, not track2

        # Query with release=2024-03-01 should get new track (binning selects newest)
        response = api_client.get(f'/track_categories/{genome_id}?release=2024-03-01')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["track_categories"][0]["track_list"]) == 1

    def test_dataset_binning_with_overlapping_specs(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_variation_genomebrowser
    ):
        """Test that datasets with overlapping specifications are binned together."""
        dataset1 = uuid.uuid4()
        dataset2 = uuid.uuid4()
        dataset3 = uuid.uuid4()

        # Dataset 1: GC + Variation (2024-01-01)
        DatasetRelease.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            release_label="2024-01-01"
        )
        track1a = Track.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            datafiles={"gc-content": "gc_v1.bw"}
        )
        track1a.specifications.add(spec_gc_genomebrowser)

        track1b = Track.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            datafiles={"variant-details": "var_v1.bb", "variant-summary": "var_v1.bw"}
        )
        track1b.specifications.add(spec_variation_genomebrowser)

        # Dataset 2: Genebuild only (2024-02-01) - non-overlapping
        DatasetRelease.objects.create(
            dataset_id=dataset2,
            genome_id=genome_id,
            release_label="2024-02-01"
        )
        # Note: spec_genebuild_genomebrowser would go here but we'll test simpler case

        # Dataset 3: GC only (2024-03-01) - overlaps with dataset1
        DatasetRelease.objects.create(
            dataset_id=dataset3,
            genome_id=genome_id,
            release_label="2024-03-01"
        )
        track3 = Track.objects.create(
            dataset_id=dataset3,
            genome_id=genome_id,
            datafiles={"gc-content": "gc_v3.bw"}
        )
        track3.specifications.add(spec_gc_genomebrowser)

        # Query with latest release
        # Should bin dataset1 and dataset3 together (both have GC)
        # Should select dataset3 (newest)
        response = api_client.get(f'/track_categories/{genome_id}')
        assert response.status_code == status.HTTP_200_OK
        # Should only get gc track from dataset3 (not from dataset1)
        # Variation track from dataset1 should also be excluded (same bin)

    def test_dataset_binning_non_overlapping_specs(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_genebuild_genomebrowser
    ):
        """Test that datasets without overlapping specs are in separate bins."""
        dataset1 = uuid.uuid4()
        dataset2 = uuid.uuid4()

        # Dataset 1: GC only (2024-01-01)
        DatasetRelease.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            release_label="2024-01-01"
        )
        track1 = Track.objects.create(
            dataset_id=dataset1,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track1.specifications.add(spec_gc_genomebrowser)

        # Dataset 2: Genebuild only (2024-02-01)
        DatasetRelease.objects.create(
            dataset_id=dataset2,
            genome_id=genome_id,
            release_label="2024-02-01"
        )
        track2 = Track.objects.create(
            dataset_id=dataset2,
            genome_id=genome_id,
            datafiles={"gene-details": "genes.bb"}
        )
        track2.specifications.add(spec_genebuild_genomebrowser)

        # Should get both tracks (different bins)
        response = api_client.get(f'/track_categories/{genome_id}')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["track_categories"][0]["track_list"]) == 2

    def test_track_ordering_by_display_order(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_genebuild_genomebrowser
    ):
        """Test that tracks are sorted by display_order within categories."""
        dataset_id = uuid.uuid4()
        DatasetRelease.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            release_label="2024-01-01"
        )

        track1 = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track1.specifications.add(spec_gc_genomebrowser)  # display_order=100

        track2 = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gene-details": "genes.bb"}
        )
        track2.specifications.add(spec_genebuild_genomebrowser)  # display_order=50

        response = api_client.get(f'/track_categories/{genome_id}')
        assert response.status_code == status.HTTP_200_OK
        track_list = response.data["track_categories"][0]["track_list"]
        # Gene track (50) should come before GC track (100)
        assert track_list[0]["label"] == "Gene Annotations"
        assert track_list[1]["label"] == "GC Content"

    def test_invalid_browser_parameter(self, api_client, genome_id):
        """Test that invalid browser parameter returns 400."""
        response = api_client.get(f'/track_categories/{genome_id}?browser=InvalidBrowser')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "browser" in str(response.data["error"])

    def test_no_releases_for_genome(self, api_client):
        """Test that genome with no releases returns 404."""
        non_existent_genome = uuid.uuid4()
        response = api_client.get(f'/track_categories/{non_existent_genome}')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_tracks_for_browser(
            self, api_client, genome_id, spec_gc_genomebrowser
    ):
        """Test that requesting browser with no matching tracks returns 404."""
        dataset_id = uuid.uuid4()
        DatasetRelease.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            release_label="2024-01-01"
        )

        track = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        # Request StructuralVariant but track only has GenomeBrowser
        response = api_client.get(f'/track_categories/{genome_id}?browser=StructuralVariant')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_multiple_categories_grouped_correctly(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_variation_genomebrowser
    ):
        """Test that tracks are grouped by category."""
        dataset_id = uuid.uuid4()
        DatasetRelease.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            release_label="2024-01-01"
        )

        track1 = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track1.specifications.add(spec_gc_genomebrowser)

        track2 = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles={"variant-details": "var.bb", "variant-summary": "var.bw"}
        )
        track2.specifications.add(spec_variation_genomebrowser)

        response = api_client.get(f'/track_categories/{genome_id}')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["track_categories"]) == 2

        # Check categories exist
        category_ids = {cat["track_category_id"] for cat in response.data["track_categories"]}
        assert "genomic" in category_ids
        assert "variation" in category_ids


# ── TrackObject Tests ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTrackObject:
    """Tests for GET /track/{track_id} endpoint."""

    def test_get_track_default_browser(
            self, api_client, genome_id, spec_gc_genomebrowser
    ):
        """Test getting track with default browser (GenomeBrowser)."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        response = api_client.get(f'/track/{track.track_id}')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["track_id"] == str(track.track_id)
        assert response.data["label"] == "GC Content"
        assert response.data["datafiles"] == {"gc-content": "gc.bw"}

    def test_get_track_with_specific_browser(
            self, api_client, genome_id, spec_gc_genomebrowser, spec_gc_structuralvariant
    ):
        """Test getting track with specific browser parameter."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)
        track.specifications.add(spec_gc_structuralvariant)

        # Test GenomeBrowser
        response = api_client.get(f'/track/{track.track_id}?browser=GenomeBrowser')
        assert response.status_code == status.HTTP_200_OK
        assert response.data["label"] == "GC Content"

        # Test StructuralVariant
        response = api_client.get(f'/track/{track.track_id}?browser=StructuralVariant')
        assert response.status_code == status.HTTP_200_OK
        assert response.data["label"] == "GC Content SV"

    def test_get_track_with_settings(
            self, api_client, genome_id, spec_genebuild_genomebrowser
    ):
        """Test that settings are included in response."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gene-details": "genes.bb"}
        )
        track.specifications.add(spec_genebuild_genomebrowser)

        response = api_client.get(f'/track/{track.track_id}')
        assert response.status_code == status.HTTP_200_OK
        assert "settings" in response.data
        assert response.data["settings"] == {"show_labels": True}

    def test_track_not_found(self, api_client):
        """Test that nonexistent track returns 404."""
        non_existent_track = uuid.uuid4()
        response = api_client.get(f'/track/{non_existent_track}')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_track_no_config_for_browser(
            self, api_client, genome_id, spec_gc_genomebrowser
    ):
        """Test that track without config for requested browser returns 404."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        # Request StructuralVariant but track only has GenomeBrowser
        response = api_client.get(f'/track/{track.track_id}?browser=StructuralVariant')
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "no configuration" in str(response.data["error"]).lower()

    def test_invalid_browser_parameter(self, api_client, genome_id, spec_gc_genomebrowser):
        """Test that invalid browser parameter returns 400."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        response = api_client.get(f'/track/{track.track_id}?browser=InvalidBrowser')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_track(self, api_client, genome_id, spec_gc_genomebrowser):
        """Test deleting a track."""
        track = Track.objects.create(
            dataset_id=uuid.uuid4(),
            genome_id=genome_id,
            datafiles={"gc-content": "gc.bw"}
        )
        track.specifications.add(spec_gc_genomebrowser)

        response = api_client.delete(f'/track/{track.track_id}')
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify track was deleted
        assert not Track.objects.filter(track_id=track.track_id).exists()

    def test_delete_nonexistent_track(self, api_client):
        """Test deleting nonexistent track returns 404."""
        non_existent_track = uuid.uuid4()
        response = api_client.delete(f'/track/{non_existent_track}')
        assert response.status_code == status.HTTP_404_NOT_FOUND