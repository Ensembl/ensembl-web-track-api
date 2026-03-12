# See the NOTICE file distributed with this work for additional information
#   regarding copyright ownership.
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#       http://www.apache.org/licenses/LICENSE-2.0
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
import os
import sys
from pathlib import Path

import django

from ensembl.production.metadata.api.models import (
    Dataset, DatasetStatus, EnsemblRelease, Genome, GenomeDataset
)
from ensembl.utils.database import DBConnection


def populate_dataset_releases(metadata_uri: str) -> int:
    """
    Clears and repopulates DatasetRelease table from ensembl_genome_metadata database.
    Returns the number of rows inserted.
    """
    #Don't move this to the top. Django settings has to be imported first to use its models.
    from tracks.models import DatasetRelease, Track

    track_dataset_uuids = list(
        Track.objects.values_list("dataset_id", flat=True).distinct()
    )
    print(f"Found {len(track_dataset_uuids)} dataset UUIDs in Track table")

    if not track_dataset_uuids:
        print("No datasets found in Track table, aborting.")
        return 0

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
            .filter(EnsemblRelease.release_type == "partial") #TODO: Make sure it works with integrated!!!
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
        default="ensembl_track_api.settings",
        help="Django settings module (default: ensembl_track_api.settings)",
    )
    args = parser.parse_args()
    # Setup Django
    # Assume script is run from project root, or use DJANGO_PROJECT_ROOT env var
    project_root = os.getenv('DJANGO_PROJECT_ROOT', os.getcwd())
    sys.path.insert(0, project_root)

    # Load .env file if it exists
    env_file = Path(project_root) / '.env'
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', args.django_settings)
    django.setup()

    count = populate_dataset_releases(args.metadata_uri)
    print(f"Successfully inserted {count} rows")
