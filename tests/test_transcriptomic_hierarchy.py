"""V3 handover preparation, recursive grouping and repeatable seeding."""

import io
import json
import uuid
from copy import deepcopy

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tracks.models import Source, Track, TranscriptomicConfiguration
from tracks.management.commands.seed_transcriptomic_configuration import (
    assembly_datafiles,
)
from tracks.transcriptomic import build_selection_hierarchy, prepare_configuration


def selection(identifier, levels, metadata, **provenance):
    return {
        "selection_id": identifier,
        "selection_hierarchy": levels,
        "metadata": {key: {"value": value} for key, value in metadata.items()},
        "provenance": provenance,
    }


def test_hierarchy_keeps_order_and_case_and_supports_direct_and_child_tracks():
    records = [
        selection("aggregate", ["study"], {"study": "Project"}),
        selection(
            "run",
            ["study", "biosample", "run"],
            {"study": "Project"},
            biosample_accession="sample",
            run_accessions=["RUN1"],
        ),
        selection("other", ["study"], {"study": "project"}),
    ]
    original = deepcopy(records)
    tree = build_selection_hierarchy(records)
    assert [(node["value"], node["selection_ids"]) for node in tree] == [
        ("Project", ["aggregate"]),
        ("project", ["other"]),
    ]
    sample = tree[0]["children"][0]
    assert (sample["level"], sample["display_label"]) == ("biosample", "sample")
    assert sample["children"][0] == {
        "level": "run",
        "value": "RUN1",
        "display_label": "RUN1",
        "selection_ids": ["run"],
        "children": [],
    }
    assert records == original


def test_missing_metadata_keeps_a_null_group():
    assert build_selection_hierarchy([selection("missing", ["tissue"], {})]) == [
        {
            "level": "tissue",
            "value": None,
            "display_label": None,
            "selection_ids": ["missing"],
            "children": [],
        }
    ]
    assert build_selection_hierarchy([]) == []


@pytest.mark.parametrize("levels", [[], [None], ["biosample"], ["run"]])
def test_invalid_hierarchy_or_missing_relationship_is_rejected(levels):
    with pytest.raises(ValueError):
        build_selection_hierarchy([selection("run", levels, {})])
    with pytest.raises(ValueError, match="Duplicate selection_id"):
        build_selection_hierarchy([selection("run", ["study"], {})] * 2)


@pytest.fixture
def records():
    genome_id = str(uuid.uuid4())
    products = [
        ("bigwig", "coverage_forward", "summary", "bw"),
        ("bigwig", "coverage_reverse", "summary", "bw"),
        ("bigbed", "splice_junction", "details", "bb"),
        ("bigbed", "gene_model", "details", "bb"),
    ]
    result = []
    for file_format, directory, role, extension in products:
        name = f"run-{directory}"
        path = f"/input/GCA_000003025.6/RUN1/{directory}/RUN1.{extension}"
        result.append(
            {
                "assembly_uuid": genome_id,
                "description": f"{directory} for RUN1.",
                "track_source": {
                    "name": "Test archive",
                    "url": "https://example.org/RUN1",
                    "details": "Run RUN1",
                },
                "dataset_source": {"name": path, "type": file_format},
                "track_files": {role: path},
                "track_metadata_payload": {
                    **selection(
                        name,
                        ["tissue", "biosample", "run"],
                        {"tissue": "Liver"},
                        biosample_accession="SAMPLE1",
                        run_accessions=["RUN1"],
                    ),
                    "schema_version": "transcriptomic-selection-0.3.1",
                    "display_label": "RUN1",
                    "selection_level": "run",
                    "data_type": "rnaseq",
                    "target_genome": {
                        "species": "Sus scrofa",
                        "assembly": "GCA_000003025.6",
                        "assembly_uuid": genome_id,
                    },
                },
            }
        )
    return result


@pytest.mark.parametrize("identifier", ["RUN1", "tissue_liver"])
def test_datafiles_use_product_directories_for_runs_and_aggregates(records, identifier):
    genome_id = records[0]["assembly_uuid"]
    for record in records:
        record["track_files"] = {
            role: path.replace("RUN1", identifier)
            for role, path in record["track_files"].items()
        }
        role, source = next(iter(record["track_files"].items()))
        product, filename = source.split("/")[-2:]
        assert assembly_datafiles(record) == {
            role: f"{genome_id[:3]}/{genome_id}/{product}/{filename}"
        }


@pytest.mark.parametrize(
    "suffix",
    [
        "tissue_liver/coverage_forward/tissue_liver.forward.bw",
        "RUN1/coverage_forward/other.forward.bw",
        "coverage_forward/RUN1.forward.bw",
    ],
)
def test_datafiles_use_only_the_product_directory_and_filename(records, suffix):
    record = records[0]
    record["track_files"] = {"summary": f"/input/GCA_000003025.6/{suffix}"}
    genome_id = record["assembly_uuid"]
    product, filename = suffix.split("/")[-2:]
    assert assembly_datafiles(record) == {
        "summary": f"{genome_id[:3]}/{genome_id}/{product}/{filename}"
    }


@pytest.mark.parametrize("suffix", ["", "/file.bw"])
def test_datafiles_require_a_product_directory_and_filename(records, suffix):
    record = records[0]
    record["track_files"] = {"summary": f"/input/GCA_000003025.6{suffix}"}
    with pytest.raises(CommandError, match="Missing product directory or filename"):
        assembly_datafiles(record)


def test_preparation_flattens_metadata_and_counts_physical_tracks(records):
    original = deepcopy(records)
    prepared = prepare_configuration(records)
    assert prepared["track_count"] == 4
    assert prepared["filters"] == {"tissue": [{"value": "Liver", "count": 4}]}
    assert all(s["metadata"] == {"tissue": "Liver"} for s in prepared["selections"])
    assert {s["track_products"][0]["track_type"] for s in prepared["selections"]} == {
        "bigwig",
        "bigbed",
    }
    assert [s["track_products"][0]["description"] for s in prepared["selections"]] == [
        record["description"] for record in records
    ]
    assert prepared["selection_hierarchy"] == build_selection_hierarchy(
        [r["track_metadata_payload"] for r in records]
    )
    assert records == original


def test_description_is_optional_but_must_be_text(records):
    del records[0]["description"]
    assert (
        prepare_configuration(records)["selections"][0]["track_products"][0][
            "description"
        ]
        == ""
    )
    records[0]["description"] = {"invalid": "description"}
    with pytest.raises(TypeError, match="description must be a string"):
        prepare_configuration(records)


def test_new_seed_and_identical_retry_keep_uuids(db, records, tmp_path):
    path = tmp_path / "records.json"
    path.write_text(json.dumps(records))
    genome_id = uuid.UUID(records[0]["assembly_uuid"])
    options = {
        "genome_id": genome_id,
        "records": path,
        "release": "2026-11-16",
        "stdout": io.StringIO(),
    }
    call_command("seed_transcriptomic_configuration", **options)
    before = list(Track.objects.order_by("pk").values())
    assert len(before) == len({track["dataset_id"] for track in before}) == 4
    for track in before:
        assert set(track["datafiles"]) in (
            {"rnaseq-coverage"},
            {"rnaseq-gene-model"},
            {"rnaseq-splice-junction"},
        )
        assert next(iter(track["datafiles"].values())).startswith(
            f"{str(genome_id)[:3]}/{genome_id}/"
        )
        # Re-importing an existing catalogue repairs its paths without new UUIDs.
        old_datafiles = {
            role: path.replace(f"/{genome_id}/", f"/{genome_id}/RUN1/")
            for role, path in track["datafiles"].items()
        }
        Track.objects.filter(pk=track["id"]).update(datafiles=old_datafiles)
    call_command("seed_transcriptomic_configuration", **options)
    assert list(Track.objects.order_by("pk").values()) == before
    for track in Track.objects.prefetch_related("specifications"):
        program = next(iter(track.datafiles))
        assert [spec.name for spec in track.specifications.all()] == [
            f"{program}-genomebrowser"
        ]
        assert list(track.sources.values("name", "url", "details")) == [
            records[0]["track_source"]
        ]
    assert Source.objects.count() == 1
    config = TranscriptomicConfiguration.objects.get()
    assert config.track_count == 4
    assert (
        config.configuration["selection_hierarchy"]
        == prepare_configuration(records)["selection_hierarchy"]
    )


def test_seed_updates_descriptions_and_replaces_source_associations(
    db, records, tmp_path
):
    path = tmp_path / "records.json"
    options = {
        "genome_id": uuid.UUID(records[0]["assembly_uuid"]),
        "records": path,
        "release": "2026-11",
        "stdout": io.StringIO(),
    }
    path.write_text(json.dumps(records))
    call_command("seed_transcriptomic_configuration", **options)
    ids = list(Track.objects.order_by("pk").values_list("track_id", flat=True))
    records[0]["description"] = "Updated coverage description."
    records[0]["track_source"]["url"] = "https://example.org/updated"
    del records[1]["track_source"]
    path.write_text(json.dumps(records))
    call_command("seed_transcriptomic_configuration", **options)
    assert list(Track.objects.order_by("pk").values_list("track_id", flat=True)) == ids
    assert list(
        Track.objects.get(track_id=ids[0]).sources.values_list("url", flat=True)
    ) == ["https://example.org/updated"]
    assert not Track.objects.get(track_id=ids[1]).sources.exists()
    configuration = TranscriptomicConfiguration.objects.get().configuration
    assert (
        configuration["selections"][0]["track_products"][0]["description"]
        == "Updated coverage description."
    )
