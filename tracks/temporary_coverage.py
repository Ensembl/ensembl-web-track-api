"""Temporary response override for the Pig RNA-seq coverage test tracks.
This is a temporary fix to address the codon cluster outage.
Remove this module and its TrackObject hook once Track API sqlite db has been updated.
"""

from pathlib import PurePosixPath

from tracks.models import TranscriptomicConfiguration

PIG_GENOME_ID = "da38d82b-df50-419b-af74-886463b7bfa3"


def override_pig_coverage(track, payload):
    if str(track.genome_id) != PIG_GENOME_ID:
        return
    filepath = payload.get("datafiles", {}).get("rnaseq_coverage")
    if not isinstance(filepath, str) or not filepath:
        return

    configuration = (
        TranscriptomicConfiguration.objects.filter(
            genome_id=track.genome_id, dataset_id=track.dataset_id
        )
        .values_list("configuration", flat=True)
        .first()
    )
    if configuration is None:
        return

    track_id = str(track.track_id)
    for selection in configuration.get("selections", []):
        if (
            selection.get("selection_level") != "run"
            or selection.get("data_type") != "rnaseq"
        ):
            continue
        if not any(
            product.get("track_type") == "rnaseq_coverage"
            and product.get("track_id") == track_id
            for product in selection.get("track_products", [])
        ):
            continue

        payload["label"] = selection["selection_id"]
        payload["additional_info"] = selection.get("metadata", {}).get("tissue", "")
        payload["datafiles"] = {
            "rnaseq_coverage": (
                f"{PIG_GENOME_ID[:3]}/{PIG_GENOME_ID}/{PurePosixPath(filepath).name}"
            )
        }
        return
