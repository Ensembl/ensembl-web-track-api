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

import uuid

import pytest

from src.ensembl.production.tracks.load_tracks import create_single_track
from tracks.models import Category, Source, Specifications, Track


@pytest.fixture
def category():
    return Category.objects.create(
        label="Test Category",
        track_category_id="test-category",
        type="Genomic"
    )


@pytest.fixture
def specification_two_files(category):
    return Specifications.objects.create(
        name="test-spec-two-files",
        label="Test Spec Two Files",
        category=category,
        trigger=["track", "test"],
        type="regular",
        files=["detail-file", "summary-file"],
        browser="GenomeBrowser"
    )


@pytest.mark.django_db
def test_create_single_track_with_sources_reuses_existing_source(specification_two_files):
    existing_source = Source.objects.create(
        name="GENCODE",
        url="https://gencodegenes.org",
        details="Comprehensive annotation"
    )

    result = create_single_track({
        "dataset_id": str(uuid.uuid4()),
        "genome_id": str(uuid.uuid4()),
        "datafiles": ["file1.bb", "file2.bw"],
        "track_types": ["test-spec-two-files"],
        "sources": [
            {
                "name": "GENCODE",
                "url": "https://gencodegenes.org",
                "details": "Comprehensive annotation"
            },
            {
                "name": "Ensembl",
                "url": "https://www.ensembl.org",
                "details": "Gene build"
            }
        ]
    })

    assert result["status"] == "success"

    track = Track.objects.get(track_id=result["track_id"])
    assert track.sources.count() == 2
    assert track.sources.filter(id=existing_source.id).exists()
    assert Source.objects.count() == 2
