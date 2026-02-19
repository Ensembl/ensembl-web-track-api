import argparse
import os
import django

from ensembl.production.metadata.api.models import (
    Dataset, DatasetStatus, EnsemblRelease, Genome, GenomeDataset
)
from ensembl.utils.database import DBConnection


def populate_dataset_releases(metadata_uri: str) -> int:
    """
    Clears and repopulates DatasetRelease table.
    Returns the number of rows inserted.
    """
    # Django imports here so django.setup() has already been called
    # whether we're running via manage.py or standalone
    from tracks.models import DatasetRelease, Track

    track_dataset_uuids = list(
        Track.objects.values_list("dataset_id", flat=True).distinct()
    )
    print(f"Found {len(track_dataset_uuids)} dataset UUIDs in Track table")

    if not track_dataset_uuids:
        print("No datasets found in Track table, aborting.")
        return 0

    # Convert to strings for SQLAlchemy comparison
    track_dataset_uuids_str = [str(u) for u in track_dataset_uuids]

    DatasetRelease.objects.all().delete()

    metadata_db = DBConnection(metadata_uri)
    with metadata_db.session_scope() as session:
        rows = (
            session.query(
                Genome.genome_uuid,
                Dataset.dataset_uuid,
                EnsemblRelease.label
            )
            .join(GenomeDataset, Genome.genome_id == GenomeDataset.genome_id)
            .join(Dataset, Dataset.dataset_id == GenomeDataset.dataset_id)
            .join(EnsemblRelease, EnsemblRelease.release_id == GenomeDataset.release_id)
            .filter(Dataset.status == DatasetStatus.RELEASED)
            .filter(Dataset.dataset_uuid.in_(track_dataset_uuids_str))
            .all()
        )

    print(f"Metadata query returned {len(rows)} rows")

    created = DatasetRelease.objects.bulk_create(
        [
            DatasetRelease(
                dataset_id=row.dataset_uuid,
                genome_id=row.genome_uuid,
                release_label=row.label,
            )
            for row in rows
        ],
        ignore_conflicts=True,
    )

    return len(created)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Populate DatasetRelease table from Ensembl metadata DB"
    )
    parser.add_argument(
        "--metadata-uri",
        required=True,
        help="SQLAlchemy URI for the metadata database",
    )
    parser.add_argument(
        "--django-settings",
        default="trackapi.settings",
        help="Django settings module (default: ensembl_track_api.settings)",
    )
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.django_settings)
    django.setup()  # Must happen before any tracks.models imports

    count = populate_dataset_releases(args.metadata_uri)
    print(f"Successfully inserted {count} rows")