"""Preparation of the current run-level RNA-seq coverage handover."""

from collections import Counter, defaultdict
from copy import deepcopy
import re


def prepare_configuration(records):
    """Validate the coverage pilot and count records, preserving source metadata.

    This deliberately accepts the current string-valued run-level handover.
    New selection levels and metadata shapes require an explicit extension.
    """
    if not isinstance(records, list) or not records:
        raise ValueError("Expected a non-empty list of selection records.")

    identifiers = set()
    assemblies = set()
    counts = defaultdict(Counter)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Record {index} must be an object.")
        for key in ("selection_id", "parent_sample_id", "display_label"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError(f"Record {index}: missing or invalid {key}.")

        selection_id = record["selection_id"]
        if selection_id in identifiers:
            raise ValueError(f"Duplicate selection_id: {selection_id}")

        identifiers.add(selection_id)
        if (
            record.get("schema_version") != "transcriptomic-selection-0.1"
            or record.get("selection_level") != "run"
            or record.get("data_type") != "rnaseq"
        ):
            raise ValueError(
                f"{selection_id}: expected a current run-level RNA-seq record."
            )

        genome = record.get("target_genome")
        if not isinstance(genome, dict) or not all(
            isinstance(genome.get(key), str) and genome[key]
            for key in ("species", "assembly")
        ):
            raise ValueError(f"{selection_id}: missing target species/assembly.")

        assemblies.add(genome["assembly"])
        provenance = record.get("provenance", {})
        if (
            not isinstance(provenance, dict)
            or provenance.get("biosample_accession") != record["parent_sample_id"]
            or provenance.get("run_accessions") != [selection_id]
        ):
            raise ValueError(f"{selection_id}: inconsistent sample/run provenance.")

        products = record.get("track_products")
        if not isinstance(products, list) or len(products) != 1:
            raise ValueError(f"{selection_id}: expected one coverage product.")
        product = products[0]
        if not isinstance(product, dict) or (
            product.get("track_type"),
            product.get("format"),
            product.get("status"),
        ) != ("rnaseq_coverage", "BigWig", "available"):
            raise ValueError(f"{selection_id}: expected an available coverage BigWig.")
        if not isinstance(product.get("track_file"), str) or not product["track_file"]:
            raise ValueError(f"{selection_id}: missing track_file.")
        if not isinstance(product.get("md5"), str) or not re.fullmatch(
            r"[0-9a-f]{32}", product["md5"]
        ):
            raise ValueError(f"{selection_id}: missing or invalid md5.")

        metadata = record.get("metadata")
        if not isinstance(metadata, dict) or any(
            not isinstance(v, str) for v in metadata.values()
        ):
            raise ValueError(
                f"{selection_id}: this importer requires string metadata values."
            )

        for key, value in metadata.items():
            counts[key][value.casefold()] += 1

    if len(assemblies) != 1:
        raise ValueError("One genome configuration must contain exactly one assembly.")

    return {
        "track_count": len(records),
        "filters": {
            key: [
                {"value": value, "count": count}
                for value, count in sorted(values.items())
            ]
            for key, values in sorted(counts.items())
        },
        "selections": deepcopy(records),
    }
