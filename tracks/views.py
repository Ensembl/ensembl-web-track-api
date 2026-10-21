#
#  See the NOTICE file distributed with this work for additional information
#  regarding copyright ownership.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
from collections import defaultdict
from typing import TypedDict
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tracks.models import (
    DatasetRelease,
    Specifications,
    Track,
    TranscriptomicConfiguration,
)
from tracks.serializers import (
    CategorySerializer,
    CreateTrackSerializer,
    LinkTypeToTrackSerializer,
)
from tracks.transcriptomic_rendering import rendering_metadata_for_tracks
from utils.redis_cache import redis_cache

logger = logging.getLogger(__name__)

# ── Helper Functions ──────────────────────────────────────────────────────────


def get_target_release(genome_id: str, release_param: str | None = None) -> str:
    """
    Determine the target release label to use for filtering.

    Args:
        genome_id: UUID of the genome
        release_param: Optional release label from query params

    Returns:
        Release label string (YYYY-MM-DD format)

    Raises:
        ValueError: If no releases found for this genome
    """
    if release_param:
        return release_param

    # Get most recent release for this genome
    latest = (
        DatasetRelease.objects.filter(genome_id=genome_id)
        .order_by("-release_label")
        .first()
    )

    if not latest:
        raise ValueError(f"No releases found for genome {genome_id}")

    return latest.release_label


class DatasetReleaseRow(TypedDict):
    dataset_id: UUID
    release_label: str


def get_datasets_up_to_release(
    genome_id: str, target_release: str
) -> list[DatasetReleaseRow]:
    """
    Get all datasets for a genome up to and including target release.

    Args:
        genome_id: UUID of the genome
        target_release: Maximum release label to include

    Returns:
        List of dicts with dataset_id and release_label
    """
    datasets = (
        DatasetRelease.objects.filter(
            genome_id=genome_id, release_label__lte=target_release
        )
        .values("dataset_id", "release_label")
        .order_by("-release_label")
    )

    return list(datasets)


def get_specifications_for_datasets(
    dataset_ids: list[str], browser: str
) -> dict[str, set[str]]:
    """
    Build a mapping of dataset_id -> set of specification names for that browser.

    Args:
        dataset_ids: List of dataset UUIDs
        browser: Browser type to filter specifications

    Returns:
        Dict mapping dataset_id to set of specification names
    """
    tracks = Track.objects.filter(dataset_id__in=dataset_ids).prefetch_related(
        Prefetch(
            "specifications",
            queryset=Specifications.objects.filter(browser=browser),
            to_attr="browser_specifications",
        )
    )

    dataset_specs = defaultdict(set)

    for track in tracks:
        specs = track.browser_specifications
        for spec in specs:
            dataset_specs[str(track.dataset_id)].add(spec.name)

    return dict(dataset_specs)


def bin_datasets_by_overlapping_specs(
    datasets: list[dict], dataset_specs: dict[str, set[str]]
) -> list[list[dict]]:
    """
    Bin datasets that share any specifications.
    Uses Union-Find algorithm for efficient grouping.

    Args:
        datasets: List of dataset dicts with dataset_id and release_label
        dataset_specs: Mapping of dataset_id -> set of spec names

    Returns:
        List of bins, where each bin is a list of dataset dicts
    """
    # Build spec -> datasets mapping
    spec_to_datasets = defaultdict(set)
    for dataset in datasets:
        dataset_id = str(dataset["dataset_id"])
        specs = dataset_specs.get(dataset_id, set())
        for spec in specs:
            spec_to_datasets[spec].add(dataset_id)

    # Union-Find: parent[dataset_id] = parent_dataset_id
    parent = {str(d["dataset_id"]): str(d["dataset_id"]) for d in datasets}

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]

    def union(x, y):
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    # Union datasets that share specs
    for spec, dataset_ids in spec_to_datasets.items():
        dataset_list = list(dataset_ids)
        for i in range(len(dataset_list) - 1):
            union(dataset_list[i], dataset_list[i + 1])

    # Group datasets by their root parent
    bins = defaultdict(list)
    for dataset in datasets:
        dataset_id = str(dataset["dataset_id"])
        root = find(dataset_id)
        bins[root].append(dataset)

    return list(bins.values())


def select_latest_dataset_from_bins(bins: list[list[dict]]) -> list[str]:
    """
    From each bin, select the dataset with the most recent release_label.

    Args:
        bins: List of bins (each bin is a list of dataset dicts)

    Returns:
        List of selected dataset_ids
    """
    selected = []
    for bin_datasets in bins:
        latest = max(bin_datasets, key=lambda d: d["release_label"])
        selected.append(str(latest["dataset_id"]))

    return selected


def combine_track_and_specification(
    track: Track, spec: Specifications, include_datafiles: bool = False
) -> dict:
    """
    Combine Track and Specification data into old API format.

    Args:
        track: Track instance
        spec: Specifications instance
        include_datafiles: Include datafiles and settings (for single track view)

    Returns:
        Dict matching old Track API format
    """
    ################# HACK WARNING ##############
    # Copy trigger from spec
    trigger = list(spec.trigger)

    # Hack for expansion tracks - append track_id if trigger[1] is "expand"
    if len(trigger) > 1 and trigger[1] == "expand":
        trigger.append(str(track.track_id))
    ################# HACK END ##################

    data = {
        "track_id": str(track.track_id),
        "label": spec.label,
        "trigger": trigger,
        "type": spec.type,
        "display_order": spec.display_order,
        "on_by_default": spec.on_by_default,
        "additional_info": spec.additional_info,
        "description": spec.description,
        "sources": [{"name": s.name, "url": s.url} for s in track.sources.all()],
    }

    if include_datafiles:
        data["datafiles"] = track.datafiles
        data["settings"] = spec.settings

    return data


def get_transcriptomic_category(genome_id: str, browser: str):
    if browser != "GenomeBrowser":
        return None

    configuration = (
        TranscriptomicConfiguration.objects.filter(
            genome_id=genome_id,
            track_count__gt=0,
            specification__browser=browser,
            specification__discovery_mode="configured",
        )
        .select_related("specification__category")
        .defer("configuration")
        .first()
    )

    if configuration is None:
        return None

    if not Track.objects.filter(
        genome_id=genome_id,
        specifications=configuration.specification,
    ).exists():
        return None

    return {
        **CategorySerializer(configuration.specification.category).data,
        "track_list": [],
    }


# ── Views ─────────────────────────────────────────────────────────────────────


class GenomeTrackList(APIView):
    """
    Retrieve inline tracks at a release and current expression availability,
    or remove all tracks for a genome.

    GET params:
        - browser: "GenomeBrowser" or "StructuralVariant" (default: GenomeBrowser)
        - release: Inline-track release label (default: most recent).
          Expression availability is independent of this parameter.
    """

    http_method_names: list[str] = ["get", "delete"]  # noqa: RUF012

    # Defaults must match the query parameter handling below.
    @redis_cache(
        "track_category_current_expression",
        params=(("browser", "GenomeBrowser"), ("release", "")),
    )
    def get(self, request, genome_id):
        browser = request.query_params.get("browser", "GenomeBrowser")
        release_param = request.query_params.get("release")

        # Validate browser
        if browser not in ["GenomeBrowser", "StructuralVariant"]:
            return Response(
                {"error": "browser must be 'GenomeBrowser' or 'StructuralVariant'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get transcriptomic category
        configured_category = get_transcriptomic_category(genome_id, browser)

        try:
            try:
                # Step 1: Determine target release
                target_release = get_target_release(genome_id, release_param)
            except ValueError:
                if configured_category is None:
                    raise
                datasets = []
            else:
                # Step 2: Get all datasets up to target release
                datasets = get_datasets_up_to_release(genome_id, target_release)

            if not datasets and configured_category is None:
                return Response(
                    {"error": "No datasets found for this genome and release."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Exclude expression-only datasets from inline deduplication.
            expression_dataset_ids = set(
                Track.objects.filter(
                    genome_id=genome_id,
                    specifications__discovery_mode="configured",
                    specifications__category__track_category_id="transcriptomic",
                ).values_list("dataset_id", flat=True)
            )

            # Preserve any dataset that also supplies existing inline tracks.
            inline_dataset_ids = set(
                Track.objects.filter(
                    genome_id=genome_id,
                    specifications__discovery_mode="inline",
                ).values_list("dataset_id", flat=True)
            )

            expression_only_dataset_ids = expression_dataset_ids - inline_dataset_ids
            datasets = [
                dataset
                for dataset in datasets
                if dataset["dataset_id"] not in expression_only_dataset_ids
            ]

            # Step 3: Get specifications for each dataset
            dataset_ids = [d["dataset_id"] for d in datasets]
            dataset_specs = get_specifications_for_datasets(dataset_ids, browser)

            # Step 4: Bin datasets by overlapping specifications
            bins = bin_datasets_by_overlapping_specs(datasets, dataset_specs)

            # Step 5: Select latest dataset from each bin
            selected_dataset_ids = select_latest_dataset_from_bins(bins)

            # Step 6: Get all inline tracks from selected datasets
            tracks = Track.objects.filter(
                genome_id=genome_id, dataset_id__in=selected_dataset_ids
            ).prefetch_related(
                Prefetch(
                    "specifications",
                    queryset=Specifications.objects.filter(
                        browser=browser, discovery_mode="inline"
                    ).select_related("category"),
                    to_attr="browser_specifications",
                ),
                "sources",
            )

            tracks = list(tracks)
            if not tracks and configured_category is None:
                return Response(
                    {"error": "No tracks found for this genome."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Step 7: For each inline track, get specification and group by category
            categories = {}

            for track in tracks:
                # Get the first specification matching the browser
                spec = (
                    track.browser_specifications[0]
                    if track.browser_specifications
                    else None
                )

                if not spec:
                    continue

                category_id = spec.category.id

                # Create category entry if not exists
                if category_id not in categories:
                    categories[category_id] = CategorySerializer(spec.category).data
                    categories[category_id]["track_list"] = []

                # Combine track + spec data
                track_data = combine_track_and_specification(track, spec)
                categories[category_id]["track_list"].append(track_data)

            # Sort track_list by display_order within each category
            for cat_data in categories.values():
                cat_data["track_list"].sort(key=lambda x: x["display_order"])

            # Step 8: Add transcriptomic category if applicable
            if configured_category is not None:
                existing = next(
                    (
                        category
                        for category in categories.values()
                        if category["track_category_id"]
                        == configured_category["track_category_id"]
                    ),
                    None,
                )
                if existing is None:
                    categories[configured_category["track_category_id"]] = (
                        configured_category
                    )

            if not categories:
                return Response(
                    {"error": "No tracks found for this genome."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Step 9: Return
            return Response(
                {"track_categories": list(categories.values())},
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            logger.warning(
                "Invalid request while retrieving tracks for genome_id=%s: %s",
                genome_id,
                e,
            )
            return Response(
                {"error": "Requested resource could not be processed."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def delete(self, request, genome_id):
        tracks = Track.objects.filter(genome_id=genome_id)
        if not tracks.exists():
            return Response(
                {"error": "No tracks found for this genome."},
                status=status.HTTP_404_NOT_FOUND,
            )
        tracks.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def browser_tracks(browser):
    return Track.objects.prefetch_related(
        Prefetch(
            "specifications",
            queryset=Specifications.objects.filter(browser=browser).order_by("pk"),
            to_attr="browser_specs",
        ),
        "sources",
    )


def track_payload(track, specification, rendering):
    data = combine_track_and_specification(track, specification, include_datafiles=True)
    data.pop("description", None)
    data.pop("additional_info", None)
    if rendering is not None:
        data.update(rendering)
    return data


class TrackBatch(APIView):
    """Backend-facing bulk form of /track/{UUID}; every requested UUID must resolve."""

    http_method_names = ["get"]  # noqa: RUF012

    @redis_cache(
        "tracks_bulk", params=(("browser", "GenomeBrowser"), ("track_ids", ""))
    )
    def get(self, request):
        browser = request.query_params.get("browser", "GenomeBrowser")
        if browser not in ("GenomeBrowser", "StructuralVariant"):
            return Response(
                {"error": "browser must be 'GenomeBrowser' or 'StructuralVariant'"},
                status=400,
            )
        values = request.query_params.get("track_ids", "").split(",")
        if not 1 <= len(values) <= 100:
            return Response(
                {"error": "Provide between 1 and 100 track UUIDs."}, status=400
            )
        try:
            track_ids = list(dict.fromkeys(str(UUID(value)) for value in values))
        except ValueError:
            return Response(
                {"error": "track_ids must be comma-separated UUIDs."}, status=400
            )
        tracks = {
            str(track.track_id): track
            for track in browser_tracks(browser).filter(track_id__in=track_ids)
        }
        missing = [track_id for track_id in track_ids if track_id not in tracks]
        if missing:
            return Response(
                {"error": "Some tracks were not found.", "track_ids": missing},
                status=404,
            )
        unconfigured = [
            track_id for track_id, track in tracks.items() if not track.browser_specs
        ]
        if unconfigured:
            return Response(
                {
                    "error": f"Tracks have no configuration for browser '{browser}'.",
                    "track_ids": unconfigured,
                },
                status=404,
            )
        rendering = rendering_metadata_for_tracks(tracks.values())
        return Response(
            {
                "tracks": [
                    track_payload(
                        tracks[track_id],
                        tracks[track_id].browser_specs[0],
                        rendering.get(track_id),
                    )
                    for track_id in track_ids
                ]
            }
        )


class TrackObject(APIView):
    """
    Retrieve a single track by track_id.

    GET params:
        - browser: "GenomeBrowser" or "StructuralVariant" (default: GenomeBrowser)
    """

    http_method_names: list[str] = ["get", "delete"]  # noqa: RUF012

    @redis_cache("track", params=(("browser", "GenomeBrowser"),))
    def get(self, request, track_id):
        browser = request.query_params.get("browser", "GenomeBrowser")

        # Validate browser
        if browser not in ["GenomeBrowser", "StructuralVariant"]:
            return Response(
                {"error": "browser must be 'GenomeBrowser' or 'StructuralVariant'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            track = browser_tracks(browser).get(track_id=track_id)
        except Track.DoesNotExist:
            return Response(
                {"error": "No track found with this track id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Filter by browser and spec name
        spec = track.browser_specs[0] if track.browser_specs else None

        if not spec:
            return Response(
                {"error": f"Track has no configuration for browser '{browser}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rendering = rendering_metadata_for_tracks([track])
        return Response(track_payload(track, spec, rendering.get(str(track.track_id))))

    def delete(self, request, track_id):
        try:
            track = Track.objects.get(track_id=track_id)
        except Track.DoesNotExist:
            return Response(
                {"error": "No track found with this track id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        track.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Ingress Views ─────────────────────────────────────────────────────────────


class CreateTrack(APIView):
    """
    Create a new track with associated types.

    POST body:
    {
        "dataset_id": "uuid",
        "genome_id": "uuid",
        "datafiles": ["file1.bb"] or ["file1.bb", "file2.bw"],
        "track_types": ["type_name1", "type_name2"],
        "sources": [
            {"name": "Source name", "url": "https://example.org", "details": "reference text"}
        ]
    }
    """

    http_method_names: list[str] = ["post"]  # noqa: RUF012

    def post(self, request):
        serializer = CreateTrackSerializer(data=request.data)
        if serializer.is_valid():
            try:
                track = serializer.save()
                return Response(
                    {"track_id": str(track.track_id)}, status=status.HTTP_201_CREATED
                )
            except IntegrityError as e:
                return Response(
                    {"error": f"Track creation failed: {e}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {"error": "Validation failed", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LinkTypeToTrack(APIView):
    """
    Link an additional type to an existing track.
    Validates that the type's files match existing types.

    POST body:
    {
        "track_id": "uuid",
        "type_name": "type_name"
    }
    """

    http_method_names: list[str] = ["post"]  # noqa: RUF012

    def post(self, request):
        serializer = LinkTypeToTrackSerializer(data=request.data)
        if serializer.is_valid():
            try:
                track = serializer.save()
                return Response(
                    {
                        "track_id": str(track.track_id),
                        "message": "Type linked successfully",
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                logger.exception("Failed to link type to track")
                return Response(
                    {"error": f"Failed to link type: {e}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {"error": "Validation failed", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TranscriptomicConfigurationView(APIView):
    """Return the current expression catalogue for a genome."""

    http_method_names: list[str] = ["get"]  # noqa: RUF012

    @redis_cache("transcriptomic_configuration_current")
    def get(self, request, genome_id):
        configuration = TranscriptomicConfiguration.objects.filter(
            genome_id=genome_id,
            track_count__gt=0,
        ).first()

        if configuration is None:
            return Response(
                {"error": "No transcriptomic configuration for this genome."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                **configuration.configuration,
                "genome_id": str(configuration.genome_id),
            }
        )
