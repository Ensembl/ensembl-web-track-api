#!/usr/bin/env python
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

"""
Standalone script to load tracks into the database.

Usage:
    python load_tracks.py tracks.json
    cat tracks.json | python load_tracks.py -

Input JSON format:
    [
        {
            "dataset_id": "550e8400-e29b-41d4-a716-446655440000",
            "genome_id": "a7335667-93e7-11ec-a39d-005056b38ce3",
            "datafiles": ["file1.bb", "file2.bw"],
            "track_types": ["type-name1", "type-name2"]
        }
    ]

Output JSON format (stdout):
    [
        {
            "dataset_id": "550e8400-e29b-41d4-a716-446655440000",
            "track_id": "d0df738a-0ecb-4b1e-8576-a5621a4b15d2",
            "specifications": ["type-name1", "type-name2"],
            "status": "success"
        },
        {
            "dataset_id": "550e8400-e29b-41d4-a716-446655440000",
            "track_id": "abc12345-0ecb-4b1e-8576-a5621a4b15d2",
            "specifications": ["type-name1", "type-name2"],
            "status": "already_exists",
            "message": "Track already exists for this dataset with these specifications"
        },
        {
            "dataset_id": "6f8bd121-0345-4b77-9dc1-d567ac13447d",
            "error": "Type(s) not found: invalid-type",
            "status": "failed"
        }
    ]
"""

import os
import sys
import json
import django
from pathlib import Path
from typing import List, Dict, Optional

# Setup Django
# Assume script is run from project root, or use DJANGO_PROJECT_ROOT env var
project_root = os.getenv('DJANGO_PROJECT_ROOT', os.getcwd())
sys.path.insert(0, project_root)

# Load .env file if it exists
env_file = Path(project_root) / '.env'
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ensembl_track_api.settings')
django.setup()

from tracks.serializers import CreateTrackSerializer
from tracks.models import Track, Specifications
from django.db import IntegrityError


def read_json_input(input_source: str) -> List[Dict]:
    """
    Read and parse JSON input from file or stdin.

    Args:
        input_source: File path or "-" for stdin

    Returns:
        List of track data dictionaries

    Raises:
        json.JSONDecodeError: If JSON is invalid
        FileNotFoundError: If file doesn't exist
    """
    if input_source == '-':
        data = json.load(sys.stdin)
    else:
        with open(input_source, 'r') as f:
            data = json.load(f)

    # Ensure we have a list
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        raise ValueError("JSON input must be a dict or list of dicts")

    return data


def check_track_exists(dataset_id: str, track_types: List[str]) -> Optional[Track]:
    """
    Check if a track already exists for this dataset with these specifications.

    Args:
        dataset_id: UUID of the dataset
        track_types: List of specification names

    Returns:
        Existing Track if found, None otherwise
    """
    # Get all tracks for this dataset
    tracks = Track.objects.filter(dataset_id=dataset_id).prefetch_related('specifications')

    # Check if any track has exactly these specifications
    for track in tracks:
        existing_spec_names = set(track.specifications.values_list('name', flat=True))
        if existing_spec_names == set(track_types):
            return track

    return None


def create_single_track(track_data: Dict, skip_duplicates: bool = True) -> Dict:
    """
    Create a single track from data dictionary.

    Args:
        track_data: Dict with dataset_id, genome_id, datafiles, track_types
        skip_duplicates: If True, skip tracks that already exist (default: True)

    Returns:
        Result dict with dataset_id, track_id, specifications, status
    """
    result = {
        "dataset_id": track_data.get("dataset_id"),
    }

    try:
        if skip_duplicates:
            existing_track = check_track_exists(
                track_data.get("dataset_id"),
                track_data.get("track_types", [])
            )

            if existing_track:
                result.update({
                    "track_id": str(existing_track.track_id),
                    "specifications": track_data.get("track_types", []),
                    "status": "already_exists",
                    "message": "Track already exists for this dataset with these specifications"
                })
                return result

        # Validate and create track
        serializer = CreateTrackSerializer(data=track_data)

        if serializer.is_valid():
            track = serializer.save()
            result.update({
                "track_id": str(track.track_id),
                "specifications": track_data.get("track_types", []),
                "status": "success"
            })
        else:
            # Validation failed
            result.update({
                "error": serializer.errors,
                "status": "failed"
            })

    except IntegrityError as e:
        result.update({
            "error": f"Database integrity error: {str(e)}",
            "status": "failed"
        })
    except Exception as e:
        result.update({
            "error": f"Unexpected error: {str(e)}",
            "status": "failed"
        })

    return result


def load_tracks(tracks_data: List[Dict], skip_duplicates: bool = True) -> List[Dict]:
    """
    Load multiple tracks from list of data dictionaries.

    Args:
        tracks_data: List of track data dicts
        skip_duplicates: If True, skip tracks that already exist

    Returns:
        List of result dicts with dataset_id, track_id, specifications, status
    """
    results = []

    for i, track_data in enumerate(tracks_data):
        try:
            result = create_single_track(track_data, skip_duplicates=skip_duplicates)
            results.append(result)
        except Exception as e:
            results.append({
                "dataset_id": track_data.get("dataset_id"),
                "error": f"Critical error processing track {i}: {str(e)}",
                "status": "failed"
            })

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Load tracks into database from JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        'input_file',
        help='JSON file with track data (use "-" for stdin)'
    )
    parser.add_argument(
        '--no-pretty',
        action='store_true',
        help='Disable pretty-print JSON output (default: pretty-print enabled)'
    )
    parser.add_argument(
        '--allow-duplicates',
        action='store_true',
        help='Allow duplicate tracks (default: skip duplicates)'
    )

    args = parser.parse_args()

    try:
        tracks_data = read_json_input(args.input_file)
    except json.JSONDecodeError as e:
        error_output = {"error": f"Invalid JSON: {e}", "status": "failed"}
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        error_output = {"error": f"File not found: {args.input_file}", "status": "failed"}
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        error_output = {"error": str(e), "status": "failed"}
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)

    # Load tracks
    results = load_tracks(tracks_data, skip_duplicates=not args.allow_duplicates)

    # Output results (pretty by default)
    if args.no_pretty:
        print(json.dumps(results))
    else:
        print(json.dumps(results, indent=2))

    success_count = sum(1 for r in results if r['status'] == 'success')
    duplicate_count = sum(1 for r in results if r['status'] == 'already_exists')
    failed_count = sum(1 for r in results if r['status'] == 'failed')

    print(
        f"Summary: {success_count} created, {duplicate_count} duplicates skipped, "
        f"{failed_count} failed (total: {len(results)})",
        file=sys.stderr
    )

    if failed_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()