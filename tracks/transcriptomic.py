"""Preparation of the transcriptomic tracks handover."""

from collections import Counter, defaultdict

TRANSCRIPTOMIC_PROGRAMS = {
    "coverage_forward": "rnaseq-coverage",
    "coverage_reverse": "rnaseq-coverage",
    "gene_model": "rnaseq-gene-model",
    "splice_junction": "rnaseq-splice-junction",
}


def hierarchy_value(selection, level):
    """Retrieve the value for a given hierarchy level from the selection."""
    provenance = selection.get("provenance", {})

    if level == "biosample":
        sample_id = provenance.get("biosample_accession")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(
                f"{selection['selection_id']}: biosample hierarchy "
                "requires a biosample_accession."
            )
        return sample_id

    if level == "run":
        runs = provenance.get("run_accessions")
        if (
            not isinstance(runs, list)
            or len(runs) != 1
            or not isinstance(runs[0], str)
            or not runs[0]
        ):
            raise ValueError(
                f"{selection['selection_id']}: run hierarchy "
                "requires exactly one run accession."
            )
        return runs[0]

    return selection.get("metadata", {}).get(level, {}).get("value")


def build_selection_hierarchy(selections):
    """Build a hierarchical representation of the given selections based on their selection_hierarchy."""
    hierarchy = []
    identifiers = set()

    for selection in selections:
        selection_id = selection["selection_id"]
        if not isinstance(selection_id, str) or not selection_id:
            raise ValueError("Missing or invalid selection_id.")
        if selection_id in identifiers:
            raise ValueError(f"Duplicate selection_id: {selection_id}")
        identifiers.add(selection_id)

        levels = selection.get("selection_hierarchy")
        if (
            not isinstance(levels, list)
            or not levels
            or any(not isinstance(level, str) or not level for level in levels)
        ):
            raise ValueError(f"{selection_id}: invalid selection_hierarchy.")

        siblings = hierarchy

        for level in levels:
            value = hierarchy_value(selection, level)
            node = next(
                (
                    candidate
                    for candidate in siblings
                    if candidate["level"] == level and candidate["value"] == value
                ),
                None,
            )

            if node is None:
                node = {
                    "level": level,
                    "value": value,
                    "display_label": value,
                    "selection_ids": [],
                    "children": [],
                }
                siblings.append(node)

            siblings = node["children"]

        node["selection_ids"].append(selection_id)

    return hierarchy


def prepare_configuration(records):
    """Validate the transcriptomic tracks handover JSON and count records."""
    if not isinstance(records, list) or not records:
        raise ValueError("Expected a non-empty list of selection records.")

    selections = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"Record {index} must be an object.")

        payload = record.get("track_metadata_payload")
        if not isinstance(payload, dict):
            raise TypeError(
                f"Record {index}: missing or invalid track_metadata_payload."
            )

        selections.append(payload)

    identifiers = set()
    assemblies = set()
    counts = defaultdict(Counter)

    for index, record in enumerate(selections):
        if not isinstance(record, dict):
            raise TypeError(f"Record {index} must be an object.")
        for key in ("selection_id", "display_label"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError(f"Record {index}: missing or invalid {key}.")

        selection_id = record["selection_id"]
        if selection_id in identifiers:
            raise ValueError(f"Duplicate selection_id: {selection_id}")
        identifiers.add(selection_id)

        # TO DO: The schema_version and data_type checks will need to be updated for future iterations of the JSON
        if record.get("schema_version") != "transcriptomic-selection-0.3.1":
            raise ValueError(f"{selection_id}: unsupported schema_version.")
        if record.get("data_type") != "rnaseq":
            raise ValueError(f"{selection_id}: expected an RNA-seq record.")

        if (
            not isinstance(record.get("selection_level"), str)
            or not record["selection_level"]
        ):
            raise ValueError(f"{selection_id}: missing or invalid selection_level.")

        genome = record.get("target_genome")
        if not isinstance(genome, dict) or not all(
            isinstance(genome.get(key), str) and genome[key]
            for key in ("species", "assembly")
        ):
            raise ValueError(f"{selection_id}: missing target species/assembly.")
        assemblies.add(genome["assembly"])

        provenance = record.get("provenance", {})
        if not isinstance(provenance, dict):
            raise TypeError(f"{selection_id}: provenance must be an object.")

        source_record = records[index]
        if not isinstance(source_record.get("description", ""), str):
            raise TypeError(f"{selection_id}: description must be a string.")
        dataset_source = source_record.get("dataset_source")
        if not isinstance(dataset_source, dict):
            raise TypeError(f"{selection_id}: missing or invalid dataset_source.")

        file_format = dataset_source.get("type")
        if not isinstance(file_format, str) or not file_format:
            raise ValueError(f"{selection_id}: missing or invalid dataset_source.type.")

        track_files = source_record.get("track_files")
        if not isinstance(track_files, dict) or not track_files:
            raise ValueError(f"{selection_id}: track_files must be a non-empty object.")

        for role, path in track_files.items():
            if not isinstance(path, str) or not path:
                raise ValueError(
                    f"{selection_id}: missing or invalid file path for {role!r}."
                )

        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise TypeError(f"{selection_id}: metadata must be an object.")

        for key, entry in metadata.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
                raise TypeError(
                    f"{selection_id}: metadata field {key!r} must contain a string value."
                )

            counts[key][entry["value"]] += 1

    if len(assemblies) != 1:
        raise ValueError("One genome configuration must contain exactly one assembly.")

    return {
        "track_count": len(records),
        "selection_hierarchy": build_selection_hierarchy(selections),
        "filters": {
            key: [
                {"value": value, "count": count}
                for value, count in sorted(values.items())
            ]
            for key, values in sorted(counts.items())
        },
        "selections": [
            {
                "selection_id": selection["selection_id"],
                "display_label": selection["display_label"],
                "selection_level": selection["selection_level"],
                "data_type": selection["data_type"],
                "metadata": {
                    key: entry["value"] for key, entry in selection["metadata"].items()
                },
                "track_products": [
                    {
                        "track_type": records[index]["dataset_source"]["type"],
                        "description": records[index].get("description", ""),
                    }
                ],
            }
            for index, selection in enumerate(selections)
        ],
    }
