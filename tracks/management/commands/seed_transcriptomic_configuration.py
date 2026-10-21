"""Register the coverage pilot and its prepared discovery configuration."""

import json
import re
import uuid
from datetime import date
from pathlib import Path, PurePosixPath

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tracks.models import (
    Category,
    DatasetRelease,
    Specifications,
    Track,
    TranscriptomicConfiguration,
)
from tracks.transcriptomic import prepare_configuration


class Command(BaseCommand):
    help = "Seed run-level coverage tracks and static counts from the Genebuild JSON."

    def add_arguments(self, parser):
        parser.add_argument("--genome-id", required=True, type=uuid.UUID)
        parser.add_argument("--records", required=True, type=Path)
        parser.add_argument(
            "--release",
            required=True,
            help="Upstream release association, YYYY-MM or YYYY-MM-DD.",
        )

    def handle(self, *args, **options):
        try:
            records = json.loads(options["records"].read_text(encoding="utf-8-sig"))
            prepared = prepare_configuration(records)
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error

        # Validate options
        genome_id = options["genome_id"]

        release = options["release"]
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?", release):
            raise CommandError("--release must use YYYY-MM or YYYY-MM-DD.")

        try:
            # Add a day only for calendar validation; preserve the release label.
            date.fromisoformat(release if len(release) == 10 else f"{release}-01")
        except ValueError as error:
            raise CommandError(
                "--release must contain a valid year, month and optional day."
            ) from error

        for record in records:
            supplied_uuid = record["target_genome"].get("genome_uuid")
            if supplied_uuid and supplied_uuid != str(genome_id):
                raise CommandError(
                    "The supplied genome UUID conflicts with the handover."
                )

        # Seed the configuration and tracks
        with transaction.atomic():
            category, _ = Category.objects.get_or_create(
                track_category_id="transcriptomic",
                defaults={"label": "Transcriptomic data", "type": "Genomic"},
            )

            spec, _ = Specifications.objects.get_or_create(
                name="rnaseq-coverage-genomebrowser",
                defaults={
                    "label": "RNA-seq coverage",
                    "category": category,
                    "browser": "GenomeBrowser",
                    "type": "regular",
                    "discovery_mode": "configured",
                    "files": ["rnaseq-coverage"],
                    "trigger": [],
                    "settings": {"rnaseq-coverage": {"scales": [0, 100, 3]}},
                    "on_by_default": False,
                    "description": "Run-level RNA-seq coverage supplied by Genebuild.",
                },
            )
            if (
                spec.category_id != category.pk
                or spec.browser != "GenomeBrowser"
                or spec.discovery_mode != "configured"
                or spec.files != ["rnaseq-coverage"]
            ):
                raise CommandError(
                    "Existing coverage specification conflicts with this importer."
                )

            config, _ = TranscriptomicConfiguration.objects.get_or_create(
                genome_id=genome_id,
                defaults={"specification": spec},
            )
            if config.specification_id != spec.pk:
                raise CommandError(
                    "This genome already has a different configured specification."
                )

            # Remember existing POC coverage datasets for later cleanup.
            old_dataset_ids = set(
                Track.objects.filter(
                    genome_id=genome_id,
                    specifications=spec,
                ).values_list("dataset_id", flat=True)
            )

            selections_by_id = {
                selection["selection_id"]: selection
                for selection in prepared["selections"]
            }
            retained_track_ids = []
            created_count = 0

            for record in records:
                product = record["track_products"][0]
                # Change absolute (handover) file paths to relative paths for Track API
                filepath = f"{str(genome_id)[:3]}/{genome_id}/{PurePosixPath(product['track_file']).name}"
                product_key = f"{record['selection_id']}:{product['track_type']}"

                # Local POC IDs only. Production uses Automation dataset IDs.
                dataset_id = uuid.uuid5(
                    genome_id, f"expression-poc-dataset:{product_key}"
                )

                track_id = uuid.uuid5(genome_id, f"expression-track:{product_key}")

                track, created = Track.objects.update_or_create(
                    track_id=track_id,
                    defaults={
                        "genome_id": genome_id,
                        "dataset_id": dataset_id,
                        "datafiles": {"rnaseq-coverage": filepath},
                    },
                )
                track.specifications.add(spec)
                retained_track_ids.append(track.track_id)
                created_count += int(created)

                selection = selections_by_id[record["selection_id"]]
                selection["track_products"][0]["track_id"] = str(track.track_id)

                # Preserve the upstream release association, without
                # using it to version or select the configuration.
                DatasetRelease.objects.get_or_create(
                    genome_id=genome_id,
                    dataset_id=dataset_id,
                    release_label=release,
                )

            # Retire POC coverage tracks absent from the replacement input.
            stale_tracks = list(
                Track.objects.filter(
                    genome_id=genome_id,
                    specifications=spec,
                ).exclude(track_id__in=retained_track_ids)
            )

            for track in stale_tracks:
                track.specifications.remove(spec)
                # Preserve a row if another specification still uses it.
                if not track.specifications.exists():
                    track.delete()

            # Remove obsolete associations only when no track for this
            # genome still uses the dataset.
            remaining_dataset_ids = set(
                Track.objects.filter(
                    genome_id=genome_id,
                    dataset_id__in=old_dataset_ids,
                ).values_list("dataset_id", flat=True)
            )
            unused_dataset_ids = old_dataset_ids - remaining_dataset_ids

            DatasetRelease.objects.filter(
                genome_id=genome_id,
                dataset_id__in=unused_dataset_ids,
            ).delete()

            config.configuration = prepared
            config.track_count = prepared["track_count"]
            config.save(update_fields=["configuration", "track_count"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {config.track_count} tracks for genome {genome_id} "
                f"({created_count} created); "
                f"retired {len(stale_tracks)} previous coverage tracks; "
                f"release association {release}. "
                "Datafiles use bucket-relative paths and "
                "rnaseq-coverage renderer settings."
            )
        )
