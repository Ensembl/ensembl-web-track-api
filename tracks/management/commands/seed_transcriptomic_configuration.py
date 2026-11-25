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


def assembly_datafiles(record):
    """Map handover files to assembly/product/filename bucket paths."""
    assembly_id = record["assembly_uuid"]
    assembly = record["track_metadata_payload"]["target_genome"]["assembly"]
    datafiles = {}

    for role, path in record["track_files"].items():
        parts = PurePosixPath(path).parts
        if parts.count(assembly) != 1:
            raise CommandError(
                f"Expected exactly one {assembly!r} directory in {path!r}."
            )

        suffix = parts[parts.index(assembly) + 1 :]
        if len(suffix) < 2:
            raise CommandError(
                f"Missing product directory or filename after {assembly!r}."
            )

        datafiles[role] = str(PurePosixPath(assembly_id[:3], assembly_id, *suffix[-2:]))

    return datafiles


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

            bigbed_spec, _ = Specifications.objects.get_or_create(
                name="rnaseq-bigbed-genomebrowser",
                defaults={
                    "label": "RNA-seq features",
                    "category": category,
                    "browser": "GenomeBrowser",
                    "type": "regular",
                    "discovery_mode": "configured",
                    "files": ["details"],
                    "trigger": [],
                    "settings": {},
                    "on_by_default": False,
                    "description": (
                        "RNA-seq gene models and splice junctions "
                        "supplied by Genebuild."
                    ),
                },
            )
            if (
                bigbed_spec.category_id != category.pk
                or bigbed_spec.browser != "GenomeBrowser"
                or bigbed_spec.discovery_mode != "configured"
                or bigbed_spec.files != ["details"]
            ):
                raise CommandError(
                    "Existing BigBed specification conflicts with this importer."
                )

            specifications_by_format = {
                "bigwig": spec,
                "bigbed": bigbed_spec,
            }

            config, _ = TranscriptomicConfiguration.objects.get_or_create(
                genome_id=genome_id,
                defaults={"specification": spec},
            )
            if config.specification_id != spec.pk:
                raise CommandError(
                    "This genome already has a different configured specification."
                )

            selections_by_id = {
                selection["selection_id"]: selection
                for selection in prepared["selections"]
            }
            created_count = 0

            for record in records:
                payload = record["track_metadata_payload"]
                selection_id = payload["selection_id"]
                selection = selections_by_id[selection_id]
                product = selection["track_products"][0]

                track_spec = specifications_by_format.get(product["track_type"])
                if track_spec is None:
                    raise CommandError(
                        f"{selection_id}: unsupported track type "
                        f"{product['track_type']!r}."
                    )

                datafiles = assembly_datafiles(record)

                if product["track_type"] == "bigwig":
                    datafiles["rnaseq-coverage"] = datafiles.pop("summary")

                product_key = f"{selection_id}:{product['track_type']}"

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
                        "datafiles": datafiles,
                    },
                )
                track.specifications.add(track_spec)
                created_count += int(created)

                product["track_id"] = str(track.track_id)

                # Preserve the upstream release association, without
                # using it to version or select the configuration.
                DatasetRelease.objects.get_or_create(
                    genome_id=genome_id,
                    dataset_id=dataset_id,
                    release_label=release,
                )

            config.configuration = prepared
            config.track_count = prepared["track_count"]
            config.save(update_fields=["configuration", "track_count"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {config.track_count} tracks for genome {genome_id} "
                f"({created_count} created); "
                f"release association {release}. "
                "Datafiles use assembly-based bucket paths."
            )
        )
