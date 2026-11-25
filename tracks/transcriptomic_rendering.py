"""Build the track rendering metadata for individual tracks and the track catalogue."""

from copy import deepcopy

from tracks.models import TranscriptomicConfiguration
from tracks.serializers import SourceSerializer
from tracks.transcriptomic import TRANSCRIPTOMIC_PROGRAMS


def transcriptomic_track_entries(payload):
    entries = {}
    for selection in payload["selections"]:
        for product in selection["track_products"]:
            entries[product["track_id"]] = selection
    return entries


def lane_orders(payload):
    """Order tracks by walking the selection hierarchy."""
    selections = {
        selection["selection_id"]: selection for selection in payload["selections"]
    }
    orders = {}

    def visit(nodes):
        for node in nodes:
            for selection_id in node["selection_ids"]:
                selection = selections[selection_id]
                for product in selection["track_products"]:
                    track_id = product["track_id"]
                    orders[track_id] = len(orders)

            visit(node["children"])

    visit(payload["selection_hierarchy"])
    return orders


def rendering_metadata(track, selection, specification, lane_order):
    product = next(
        product
        for product in selection["track_products"]
        if product["track_id"] == str(track.track_id)
    )
    metadata = {
        "genome_id": str(track.genome_id),
        "dataset_id": str(track.dataset_id),
        "label": selection["display_label"],
        "description": product["description"],
        "sources": SourceSerializer(track.sources.all(), many=True).data,
        "display_order": specification.display_order,
        "lane_order": lane_order,
        "datafiles": dict(track.datafiles),
        "settings": deepcopy(specification.settings),
    }

    if "tissue" in selection["metadata"]:
        tissue = selection["metadata"]["tissue"]
        metadata["tissue"] = tissue
        metadata["additional_info"] = tissue

    return metadata


def rendering_metadata_for_tracks(tracks):
    """Resolve configurations once per batch using each track's specification."""
    specification_names = {
        f"{program}-genomebrowser" for program in TRANSCRIPTOMIC_PROGRAMS.values()
    }

    candidates = {}
    specifications = {}

    for track in tracks:
        specification = next(
            (spec for spec in track.browser_specs if spec.name in specification_names),
            None,
        )
        if specification is None:
            continue

        track_id = str(track.track_id)
        candidates[track_id] = track
        specifications[track_id] = specification

    if not candidates:
        return {}

    genome_ids = {track.genome_id for track in candidates.values()}
    metadata = {}

    for configuration in TranscriptomicConfiguration.objects.filter(
        genome_id__in=genome_ids
    ):
        entries = transcriptomic_track_entries(configuration.configuration)
        orders = lane_orders(configuration.configuration)

        for track_id in candidates.keys() & entries.keys():
            track = candidates[track_id]
            if track.genome_id != configuration.genome_id:
                continue

            metadata[track_id] = rendering_metadata(
                track,
                entries[track_id],
                specifications[track_id],
                orders[track_id],
            )

    return metadata
