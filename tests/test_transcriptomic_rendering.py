"""Genome-wide coverage metadata across datasets, bulk lookups and discovery."""

from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from tracks.models import (
    Category,
    DatasetRelease,
    Source,
    Specifications,
    Track,
    TranscriptomicConfiguration,
)
from tracks.transcriptomic_rendering import (
    lane_orders,
    transcriptomic_track_entries,
)
from utils import redis_cache


def test_lane_order_follows_direct_selections_then_children():
    selections = [
        {"selection_id": name, "track_products": [{"track_id": name}]}
        for name in ("a", "b", "c")
    ]
    payload = {
        "selections": selections,
        "selection_hierarchy": [
            {
                "selection_ids": ["b"],
                "children": [{"selection_ids": ["c", "a"], "children": []}],
            }
        ],
    }
    assert lane_orders(payload) == {"b": 0, "c": 1, "a": 2}
    payload["selections"].reverse()
    assert lane_orders(payload) == {"b": 0, "c": 1, "a": 2}
    assert set(transcriptomic_track_entries(payload)) == {"a", "b", "c"}


@pytest.fixture
def catalogue(db):
    genome_id = uuid4()
    category = Category.objects.create(
        label="Transcriptomic data", track_category_id="transcriptomic"
    )
    specification = Specifications.objects.create(
        name="rnaseq-coverage-genomebrowser",
        label="RNA-seq coverage",
        category=category,
        browser="GenomeBrowser",
        discovery_mode="configured",
        files=["rnaseq-coverage"],
        display_order=2000,
        settings={"rnaseq-coverage": {"scales": [0, 100, 3], "switches": ["name"]}},
    )
    specifications = {"rnaseq-coverage": specification}
    for program in ("rnaseq-gene-model", "rnaseq-splice-junction"):
        specifications[program] = Specifications.objects.create(
            name=f"{program}-genomebrowser",
            label=program,
            category=category,
            browser="GenomeBrowser",
            discovery_mode="configured",
            files=[program],
            display_order=2000,
            settings={program: {"scales": [0, 100, 3]}},
        )
    selections = []
    products = [
        ("bigwig", "coverage_forward", "rnaseq-coverage", "bw"),
        ("bigwig", "coverage_reverse", "rnaseq-coverage", "bw"),
        ("bigbed", "splice_junction", "rnaseq-splice-junction", "bb"),
        ("bigbed", "gene_model", "rnaseq-gene-model", "bb"),
    ]
    for i in range(8):
        file_format, directory, role, extension = products[i % 4]
        dataset_id = uuid4()
        track = Track.objects.create(
            genome_id=genome_id,
            dataset_id=dataset_id,
            datafiles={role: f"genome/{directory}/run{i}.{extension}"},
        )
        track.specifications.add(specifications[role])
        track.sources.add(
            Source.objects.create(
                name="Test archive",
                url=f"https://example.org/RUN{i}",
                details=f"Run RUN{i}",
            )
        )
        DatasetRelease.objects.create(
            genome_id=genome_id, dataset_id=dataset_id, release_label="2026-01-01"
        )
        selections.append(
            {
                "selection_id": f"RUN{i}",
                "display_label": f"RUN{i}",
                "selection_level": "run",
                "data_type": "rnaseq",
                "metadata": {"tissue": "Liver" if i % 2 else "Brain"},
                "track_products": [
                    {
                        "track_type": file_format,
                        "track_id": str(track.track_id),
                        "description": f"Track RUN{i}.",
                    }
                ],
            }
        )
    return TranscriptomicConfiguration.objects.create(
        genome_id=genome_id,
        specification=specification,
        track_count=len(selections),
        configuration={
            "track_count": len(selections),
            "selections": selections,
            "selection_hierarchy": [
                {
                    "level": "study",
                    "value": "project",
                    "display_label": "Project",
                    "selection_ids": [s["selection_id"] for s in selections],
                    "children": [],
                }
            ],
        },
    )


def catalogue_ids(catalogue):
    return [
        selection["track_products"][0]["track_id"]
        for selection in catalogue.configuration["selections"]
    ]


def test_bulk_matches_single_records_and_preserves_request_order(
    catalogue, django_assert_num_queries
):
    client = APIClient()
    ids = catalogue_ids(catalogue)[::-1]
    with django_assert_num_queries(4):
        response = client.get("/track", {"track_ids": ",".join(ids)})
    assert response.status_code == 200
    assert [record["track_id"] for record in response.data["tracks"]] == ids
    for record in response.data["tracks"]:
        assert record == client.get(f"/track/{record['track_id']}").data
        assert (
            record["datafiles"]
            == Track.objects.get(track_id=record["track_id"]).datafiles
        )
        assert (
            record["settings"]
            == Track.objects.get(track_id=record["track_id"])
            .specifications.first()
            .settings
        )
        assert record["genome_id"] == str(catalogue.genome_id)
        selection = next(
            selection
            for selection in catalogue.configuration["selections"]
            if selection["track_products"][0]["track_id"] == record["track_id"]
        )
        assert record["description"] == selection["track_products"][0]["description"]
        assert record["sources"] == [
            {
                "name": "Test archive",
                "url": f"https://example.org/{selection['selection_id']}",
                "details": f"Run {selection['selection_id']}",
            }
        ]
        assert record["dataset_id"] == str(
            Track.objects.get(track_id=record["track_id"]).dataset_id
        )
    assert len({record["dataset_id"] for record in response.data["tracks"]}) == 8
    assert sorted(record["lane_order"] for record in response.data["tracks"]) == list(
        range(8)
    )


def test_configuration_includes_product_details_in_three_queries_without_writing(
    catalogue, django_assert_num_queries
):
    original = deepcopy(catalogue.configuration)
    with django_assert_num_queries(3):
        response = APIClient().get(
            f"/configuration/{catalogue.genome_id}/transcriptomic"
        )
    assert response.status_code == 200
    expected = deepcopy(original)
    labels = [
        "Coverage forward",
        "Coverage reverse",
        "Splice junction",
        "Gene model",
    ] * 2
    for i, (selection, label) in enumerate(zip(expected["selections"], labels)):
        selection["track_products"][0]["display_label"] = label
        selection["track_products"][0]["sources"] = [
            {
                "name": "Test archive",
                "url": f"https://example.org/RUN{i}",
                "details": f"Run RUN{i}",
            }
        ]
    assert response.data == {**expected, "genome_id": str(catalogue.genome_id)}
    for selection in response.data["selections"]:
        for product in selection["track_products"]:
            assert set(product) == {
                "track_id",
                "track_type",
                "display_label",
                "description",
                "sources",
            }
    catalogue.refresh_from_db()
    assert catalogue.configuration == original


def test_bulk_deduplicates_and_rejects_partial_results(catalogue):
    client = APIClient()
    track_id = catalogue_ids(catalogue)[0]
    response = client.get("/track", {"track_ids": f"{track_id},{track_id}"})
    assert len(response.data["tracks"]) == 1
    missing = str(uuid4())
    response = client.get("/track", {"track_ids": f"{track_id},{missing}"})
    assert response.status_code == 404
    assert response.data["track_ids"] == [missing]
    assert "tracks" not in response.data


def test_bulk_accepts_ordinary_tracks_and_multiple_catalogue_scopes(catalogue):
    ordinary_spec = Specifications.objects.create(
        name="gc",
        label="GC",
        browser="GenomeBrowser",
        files=["gc"],
        category=catalogue.specification.category,
    )
    ordinary = Track.objects.create(
        genome_id=uuid4(), dataset_id=uuid4(), datafiles={"gc": "genome/gc.bw"}
    )
    ordinary.specifications.add(ordinary_spec)
    other_genome, other_dataset = uuid4(), uuid4()
    other = Track.objects.create(
        genome_id=other_genome,
        dataset_id=other_dataset,
        datafiles={"rnaseq-coverage": "other/run.bw"},
    )
    other.specifications.add(catalogue.specification)
    TranscriptomicConfiguration.objects.create(
        genome_id=other_genome,
        specification=catalogue.specification,
        track_count=1,
        configuration={
            "selection_hierarchy": [{"selection_ids": ["OTHER_RUN"], "children": []}],
            "selections": [
                {
                    "selection_id": "OTHER_RUN",
                    "display_label": "OTHER_RUN",
                    "selection_level": "run",
                    "data_type": "rnaseq",
                    "metadata": {"tissue": "Other"},
                    "track_products": [
                        {
                            "track_type": "bigwig",
                            "track_id": str(other.track_id),
                            "description": "Other run.",
                        }
                    ],
                }
            ],
        },
    )
    ids = [catalogue_ids(catalogue)[0], str(ordinary.track_id), str(other.track_id)]
    response = APIClient().get("/track", {"track_ids": ",".join(ids)})
    assert response.status_code == 200
    first, gc, last = response.data["tracks"]
    assert first["genome_id"] == str(catalogue.genome_id)
    assert gc["label"] == "GC" and gc["datafiles"] == ordinary.datafiles
    assert "lane_order" not in gc
    assert last["genome_id"] == str(other_genome)
    assert last["dataset_id"] == str(other_dataset)
    assert last["label"] == "OTHER_RUN" and last["lane_order"] == 0


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"track_ids": ""},
        {"track_ids": "invalid"},
        {"track_ids": ",".join(str(uuid4()) for _ in range(101))},
        {"track_ids": str(uuid4()), "browser": "invalid"},
    ],
)
def test_bulk_rejects_invalid_requests(db, parameters):
    assert APIClient().get("/track", parameters).status_code == 400


def test_bulk_checks_browser_and_does_not_mix_configuration_scopes(catalogue):
    client = APIClient()
    track_id = catalogue_ids(catalogue)[0]
    response = client.get(
        "/track", {"track_ids": track_id, "browser": "StructuralVariant"}
    )
    assert response.status_code == 404
    track = Track.objects.get(track_id=track_id)
    track.genome_id = uuid4()
    track.save()
    record = client.get("/track", {"track_ids": track_id}).data["tracks"][0]
    assert "lane_order" not in record


def test_bulk_cache_reuses_one_complete_response(
    catalogue, settings, monkeypatch, django_assert_num_queries
):
    settings.ENABLE_CACHE = True
    monkeypatch.setattr(redis_cache, "_database_version", "bulk-test")
    client = APIClient()
    parameters = {"track_ids": ",".join(catalogue_ids(catalogue))}
    first = client.get("/track", parameters)
    assert first["X-Track-Cache"] == "MISS"
    with django_assert_num_queries(0):
        cached = client.get("/track", parameters)
    assert cached["X-Track-Cache"] == "HIT"
    assert cached.data == first.data
    # Membership is part of the cache key.
    subset = client.get("/track", {"track_ids": catalogue_ids(catalogue)[0]})
    assert len(subset.data["tracks"]) == 1


def test_configuration_cache_includes_product_labels(
    catalogue, settings, monkeypatch, django_assert_num_queries
):
    settings.ENABLE_CACHE = True
    monkeypatch.setattr(redis_cache, "_database_version", "configuration-labels")
    client = APIClient()
    path = f"/configuration/{catalogue.genome_id}/transcriptomic"
    with django_assert_num_queries(3):
        first = client.get(path)
    assert first["X-Track-Cache"] == "MISS"
    with django_assert_num_queries(0):
        cached = client.get(path)
    assert cached["X-Track-Cache"] == "HIT"
    assert cached.data == first.data
    assert (
        cached.data["selections"][0]["track_products"][0]["display_label"]
        == "Coverage forward"
    )


def test_configuration_and_discovery_do_not_require_release_associations(catalogue):
    DatasetRelease.objects.all().delete()
    client = APIClient()
    response = client.get(f"/configuration/{catalogue.genome_id}/transcriptomic")
    assert response.status_code == 200
    assert "dataset_id" not in response.data
    assert response.data["track_count"] == 8
    for parameters in ({}, {"release": "2000-01-01"}):
        response = client.get(f"/track_categories/{catalogue.genome_id}", parameters)
        assert response.status_code == 200
        assert response.data["track_categories"] == [
            {
                "track_category_id": "transcriptomic",
                "label": "Transcriptomic data",
                "type": "Genomic",
                "track_list": [],
            }
        ]


def test_tracks_keep_rendering_metadata_when_their_dataset_changes(catalogue):
    track_id = catalogue_ids(catalogue)[0]
    track = Track.objects.get(track_id=track_id)
    track.dataset_id = uuid4()
    track.save()
    record = APIClient().get(f"/track/{track_id}").data
    assert record["dataset_id"] == str(track.dataset_id)
    assert record["label"] == "RUN0"
    assert record["lane_order"] == 0


@pytest.mark.parametrize("same_inline_type", [False, True])
def test_coverage_does_not_change_inline_dataset_selection(catalogue, same_inline_type):
    category = Category.objects.create(
        label="Assembly", track_category_id="assembly", type="Genomic"
    )
    specifications = [
        Specifications.objects.create(
            name=f"inline-{i}",
            label=f"Inline {i}",
            category=category,
            browser="GenomeBrowser",
            files=["inline"],
        )
        for i in range(2)
    ]
    tracks = []
    for i, track_id in enumerate(catalogue_ids(catalogue)[:2]):
        dataset_id = Track.objects.get(track_id=track_id).dataset_id
        DatasetRelease.objects.filter(dataset_id=dataset_id).update(
            release_label=f"2025-0{i + 1}-01"
        )
        track = Track.objects.create(
            genome_id=catalogue.genome_id,
            dataset_id=dataset_id,
            datafiles={"inline": f"inline/{i}.bw"},
        )
        track.specifications.add(specifications[0 if same_inline_type else i])
        tracks.append(str(track.track_id))
    response = APIClient().get(f"/track_categories/{catalogue.genome_id}")
    assert response.status_code == 200
    inline = next(
        category
        for category in response.data["track_categories"]
        if category["track_category_id"] == "assembly"
    )
    assert {track["track_id"] for track in inline["track_list"]} == set(
        tracks[-1:] if same_inline_type else tracks
    )
