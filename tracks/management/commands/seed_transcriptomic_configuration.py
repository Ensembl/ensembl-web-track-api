"""Register the coverage pilot and its prepared discovery configuration."""

import json
import re
import uuid
from datetime import date
from pathlib import Path

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
            "--release", required=True, help="Release label, YYYY-MM-DD"
        )
        parser.add_argument(
            "--dataset-id",
            type=uuid.UUID,
            help="Existing dataset for an identical retry; omit to create a new version.",
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

        dataset_id = options.get("dataset_id") or uuid.uuid4()
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
                    "files": ["rnaseq_coverage"],
                    "trigger": [],
                    "settings": {},
                    "on_by_default": False,
                    "description": "Run-level RNA-seq coverage supplied by Genebuild.",
                },
            )
            if (
                spec.category_id != category.pk
                or spec.browser != "GenomeBrowser"
                or spec.discovery_mode != "configured"
                or spec.files != ["rnaseq_coverage"]
            ):
                raise CommandError(
                    "Existing coverage specification conflicts with this importer."
                )

            config, _ = TranscriptomicConfiguration.objects.get_or_create(
                genome_id=genome_id,
                dataset_id=dataset_id,
                defaults={"specification": spec},
            )
            if config.specification_id != spec.pk:
                raise CommandError(
                    "This genome already has a different configured specification."
                )

            # The existing selector has no tie-breaker for competing versions in one release.
            competing = DatasetRelease.objects.filter(
                genome_id=genome_id,
                release_label=release,
                dataset_id__in=Track.objects.filter(
                    genome_id=genome_id,
                    specifications=spec,
                ).values("dataset_id"),
            ).exclude(dataset_id=dataset_id)
            if competing.exists():
                raise CommandError(
                    "A coverage dataset already exists for this release; retry with its --dataset-id."
                )

            for record in prepared["selections"]:
                record["track_products"][0]["track_id"] = str(
                    uuid.uuid5(
                        config.dataset_id, record["selection_id"] + ":rnaseq_coverage"
                    )
                )

            if config.configuration and config.configuration != prepared:
                raise CommandError(
                    "Dataset content differs. Omit --dataset-id to create a new version at a new release."
                )

            created_count = 0
            for record in records:
                product = record["track_products"][0]

                # Retained catalogue UUID gives stable track IDs across repeated seeds.
                track_id = uuid.uuid5(
                    config.dataset_id, record["selection_id"] + ":rnaseq_coverage"
                )

                existing_track = Track.objects.filter(track_id=track_id).first()
                if existing_track is not None and existing_track.datafiles != {
                    "rnaseq_coverage": product["track_file"]
                }:
                    raise CommandError(
                        f"Track {track_id} already exists with a different file path. Omit --dataset-id to create a new version at a new release."
                    )

                track, created = Track.objects.update_or_create(
                    track_id=track_id,
                    defaults={
                        "genome_id": genome_id,
                        "dataset_id": config.dataset_id,
                        "datafiles": {"rnaseq_coverage": product["track_file"]},
                    },
                )
                track.specifications.add(spec)
                created_count += int(created)

            config.configuration = prepared
            config.track_count = prepared["track_count"]
            config.save(update_fields=["configuration", "track_count"])
            DatasetRelease.objects.get_or_create(
                genome_id=genome_id,
                dataset_id=config.dataset_id,
                release_label=release,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {config.track_count} tracks for genome {genome_id} "
                f"({created_count} created); dataset {config.dataset_id}; release {release}. "
                "File paths are preserved; trigger/settings remain unchanged."
            )
        )
