"""Build the track rendering metadata for individual tracks and the track catalogue."""

from copy import deepcopy

from django.db.models import Q

from tracks.models import TranscriptomicConfiguration


def coverage_track_entries(payload):
    entries = {}
    for selection in payload["selections"]:
        if selection["selection_level"] != "run" or selection["data_type"] != "rnaseq":
            continue
        for product in selection["track_products"]:
            if product["track_type"] == "rnaseq_coverage":
                entries.setdefault(product["track_id"], selection)
    return entries


def lane_orders(entries):
    def key(track_id):
        selection = entries[track_id]
        tissue = (selection["metadata"].get("tissue") or "").strip().casefold()
        return not bool(tissue), tissue, selection["selection_id"].casefold(), track_id

    return {track_id: order for order, track_id in enumerate(sorted(entries, key=key))}


def rendering_metadata(track, selection, specification, lane_order):
    tissue = (selection["metadata"].get("tissue") or "").strip()
    return {
        "genome_id": str(track.genome_id),
        "dataset_id": str(track.dataset_id),
        "label": selection["selection_id"],
        "run_id": selection["selection_id"],
        "tissue": tissue,
        "additional_info": tissue,
        "display_order": specification.display_order,
        "lane_order": lane_order,
        "datafiles": dict(track.datafiles),
        "settings": deepcopy(specification.settings),
    }


def rendering_metadata_for_tracks(tracks):
    """Resolve configurations once per batch."""
    coverage = {
        str(track.track_id): track
        for track in tracks
        if "rnaseq-coverage" in track.datafiles
    }
    if not coverage:
        return {}
    scope = Q()
    for genome_id, dataset_id in {
        (track.genome_id, track.dataset_id) for track in coverage.values()
    }:
        scope |= Q(genome_id=genome_id, dataset_id=dataset_id)
    metadata = {}
    for configuration in TranscriptomicConfiguration.objects.select_related(
        "specification"
    ).filter(scope):
        entries = coverage_track_entries(configuration.configuration)
        orders = lane_orders(entries)
        for track_id in coverage.keys() & entries.keys():
            track = coverage[track_id]
            if (
                track.genome_id != configuration.genome_id
                or track.dataset_id != configuration.dataset_id
                or configuration.specification_id
                not in {spec.pk for spec in track.browser_specs}
            ):
                continue
            metadata[track_id] = rendering_metadata(
                track, entries[track_id], configuration.specification, orders[track_id]
            )
    return metadata
