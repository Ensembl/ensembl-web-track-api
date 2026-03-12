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

from collections import defaultdict
from typing import Dict, List, Set
from tracks.models import Track, Category, DatasetRelease, Specifications
from tracks.serializers import (
    ReadTrackSerializer, CategorySerializer, CategoryTrackSerializer,
    LinkTypeToTrackSerializer, CreateTrackSerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError
from ensembl_track_api import settings


# ── Helper Functions ──────────────────────────────────────────────────────────

def get_target_release(genome_id: str, release_param: str = None) -> str:
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
    latest = DatasetRelease.objects.filter(
        genome_id=genome_id
    ).order_by('-release_label').first()

    if not latest:
        raise ValueError(f"No releases found for genome {genome_id}")

    return latest.release_label


def get_datasets_up_to_release(genome_id: str, target_release: str) -> List[Dict]:
    """
    Get all datasets for a genome up to and including target release.

    Args:
        genome_id: UUID of the genome
        target_release: Maximum release label to include

    Returns:
        List of dicts with dataset_id and release_label
    """
    datasets = DatasetRelease.objects.filter(
        genome_id=genome_id,
        release_label__lte=target_release
    ).values('dataset_id', 'release_label').order_by('-release_label')

    return list(datasets)


def get_specifications_for_datasets(
        dataset_ids: List[str],
        browser: str
) -> Dict[str, Set[str]]:
    """
    Build a mapping of dataset_id -> set of specification names for that browser.

    Args:
        dataset_ids: List of dataset UUIDs
        browser: Browser type to filter specifications

    Returns:
        Dict mapping dataset_id to set of specification names
    """
    # Get all tracks for these datasets
    tracks = Track.objects.filter(
        dataset_id__in=dataset_ids
    ).prefetch_related('specifications')

    dataset_specs = defaultdict(set)

    for track in tracks:
        # Get specifications matching browser
        specs = track.specifications.filter(browser=browser)
        for spec in specs:
            dataset_specs[str(track.dataset_id)].add(spec.name)

    return dict(dataset_specs)


def bin_datasets_by_overlapping_specs(
        datasets: List[Dict],
        dataset_specs: Dict[str, Set[str]]
) -> List[List[Dict]]:
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
        dataset_id = str(dataset['dataset_id'])
        specs = dataset_specs.get(dataset_id, set())
        for spec in specs:
            spec_to_datasets[spec].add(dataset_id)

    # Union-Find: parent[dataset_id] = parent_dataset_id
    parent = {str(d['dataset_id']): str(d['dataset_id']) for d in datasets}

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
        dataset_id = str(dataset['dataset_id'])
        root = find(dataset_id)
        bins[root].append(dataset)

    return list(bins.values())


def select_latest_dataset_from_bins(bins: List[List[Dict]]) -> List[str]:
    """
    From each bin, select the dataset with the most recent release_label.

    Args:
        bins: List of bins (each bin is a list of dataset dicts)

    Returns:
        List of selected dataset_ids
    """
    selected = []
    for bin_datasets in bins:
        # Get dataset with max release_label
        latest = max(bin_datasets, key=lambda d: d['release_label'])
        selected.append(str(latest['dataset_id']))

    return selected


def combine_track_and_specification(
        track: Track,
        spec: Specifications,
        include_datafiles: bool = False
) -> Dict:
    """
    Combine Track and Specification data into old API format.

    Args:
        track: Track instance
        spec: Specifications instance
        include_datafiles: Include datafiles and settings (for single track view)

    Returns:
        Dict matching old Track API format
    """
    #Hack the trigger on there
    trigger = list(spec.trigger)
    trigger.append(str(track.track_id))


    data = {
        'track_id': str(track.track_id),
        'label': spec.label,
        'trigger': trigger,
        'type': spec.type,
        'display_order': spec.display_order,
        'on_by_default': spec.on_by_default,
        'additional_info': spec.additional_info,
        'description': spec.description,
        'sources': [{'name': s.name, 'url': s.url} for s in spec.sources.all()]  # Changed from track.sources
    }

    if include_datafiles:
        data['datafiles'] = track.datafiles
        data['settings'] = spec.settings

    return data


# ── Views ─────────────────────────────────────────────────────────────────────

class GenomeTrackList(APIView):
    """
    Retrieve or remove all tracks for a genome at a specific release.

    GET params:
        - browser: "GenomeBrowser" or "StructuralVariant" (default: GenomeBrowser)
        - release: Release label YYYY-MM-DD (default: most recent)
    """
    http_method_names = ['get', 'delete']

    def get(self, request, genome_id):
        # Get parameters
        browser = request.query_params.get('browser', 'GenomeBrowser')
        release_param = request.query_params.get('release')

        # Validate browser
        if browser not in ['GenomeBrowser', 'StructuralVariant']:
            return Response(
                {"error": "browser must be 'GenomeBrowser' or 'StructuralVariant'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Step 1: Determine target release
            target_release = get_target_release(genome_id, release_param)

            # Step 2: Get all datasets up to target release
            datasets = get_datasets_up_to_release(genome_id, target_release)

            if not datasets:
                return Response(
                    {"error": "No datasets found for this genome and release."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Step 3: Get specifications for each dataset
            dataset_ids = [d['dataset_id'] for d in datasets]
            dataset_specs = get_specifications_for_datasets(dataset_ids, browser)

            # Step 4: Bin datasets by overlapping specifications
            bins = bin_datasets_by_overlapping_specs(datasets, dataset_specs)

            # Step 5: Select latest dataset from each bin
            selected_dataset_ids = select_latest_dataset_from_bins(bins)

            # Step 6: Get all tracks from selected datasets
            tracks = Track.objects.filter(
                genome_id=genome_id,
                dataset_id__in=selected_dataset_ids
            ).prefetch_related('specifications', 'specifications__category', 'specifications__sources')

            if not tracks.exists():
                return Response(
                    {"error": "No tracks found for this genome."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Step 7: For each track, get specification and group by category
            categories = {}

            for track in tracks:
                # Get ALL specifications matching browser (not just first)
                specs = track.specifications.filter(browser=browser)

                # Loop through each specification
                for spec in specs:
                    category_id = spec.category.id

                    # Create category entry if not exists
                    if category_id not in categories:
                        categories[category_id] = CategorySerializer(spec.category).data
                        categories[category_id]["track_list"] = []

                    # Combine track + spec data
                    track_data = combine_track_and_specification(track, spec)
                    categories[category_id]["track_list"].append(track_data)

            if not categories:
                return Response(
                    {"error": "No tracks found for this genome."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Sort track_list by display_order within each category
            for cat_data in categories.values():
                cat_data["track_list"].sort(key=lambda x: x['display_order'])

            # Step 8: Return
            return Response(
                {"track_categories": list(categories.values())},
                status=status.HTTP_200_OK
            )

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

    def delete(self, request, genome_id):
        tracks = Track.objects.filter(genome_id=genome_id)
        if not tracks.exists():
            return Response(
                {"error": "No tracks found for this genome."},
                status=status.HTTP_404_NOT_FOUND
            )
        tracks.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrackObject(APIView):
    """
    Retrieve a single track by track_id.

    GET params:
        - browser: "GenomeBrowser" or "StructuralVariant" (default: GenomeBrowser)
    """
    http_method_names = ['get', 'delete']

    def get(self, request, track_id):
        browser = request.query_params.get('browser', 'GenomeBrowser')
        spec_name = request.query_params.get('spec')

        # Validate spec is required
        if not spec_name:
            return Response(
                {"error": "spec parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate browser
        if browser not in ['GenomeBrowser', 'StructuralVariant']:
            return Response(
                {"error": "browser must be 'GenomeBrowser' or 'StructuralVariant'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            track = Track.objects.prefetch_related('specifications', 'specifications__sources').get(
                track_id=track_id
            )
        except Track.DoesNotExist:
            return Response(
                {"error": "No track found with this track id."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Filter by browser and spec name
        spec = track.specifications.filter(browser=browser, name=spec_name).first()

        if not spec:
            return Response(
                {"error": f"Track has no configuration for browser '{browser}' and specification '{spec_name}'."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Combine track + spec data
        track_data = combine_track_and_specification(track, spec, include_datafiles=True)
        return Response(track_data)

    def delete(self, request, track_id):
        try:
            track = Track.objects.get(track_id=track_id)
        except Track.DoesNotExist:
            return Response(
                {"error": "No track found with this track id."},
                status=status.HTTP_404_NOT_FOUND
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
        "track_types": ["type_name1", "type_name2"]
    }
    """
    http_method_names = ['post']

    def post(self, request):
        serializer = CreateTrackSerializer(data=request.data)
        if serializer.is_valid():
            try:
                track = serializer.save()
                return Response(
                    {"track_id": str(track.track_id)},
                    status=status.HTTP_201_CREATED
                )
            except IntegrityError as e:
                return Response(
                    {"error": f"Track creation failed: {e}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(
            {"error": "Validation failed", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
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
    http_method_names = ['post']

    def post(self, request):
        serializer = LinkTypeToTrackSerializer(data=request.data)
        if serializer.is_valid():
            try:
                track = serializer.save()
                return Response(
                    {
                        "track_id": str(track.track_id),
                        "message": "Type linked successfully"
                    },
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                return Response(
                    {"error": f"Failed to link type: {e}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(
            {"error": "Validation failed", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
