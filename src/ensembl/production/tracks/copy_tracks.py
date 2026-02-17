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

"""
Track file deployment module.

Copies track data files to their final location based on genome_uuid and dataset_uuid.
Designed for integration with Airflow DAGs.

Warning: NO CHECKS ARE INCLUDED
TODO: Add checks into ensembl-datachecks.py

Directory structure:
    {BASE_PATH}/{first_2_chars_of_genome_uuid}/{genome_uuid}/{dataset_uuid}_{track_name}.{extension}

Example:
    BASE_PATH/ab/abcd-1234-5678-90ef/dataset-5678-90ab_my_track.bb
"""
import argparse
import hashlib
import json
import shutil
import logging
from pathlib import Path
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrackCopyError(Exception):
    """Custom exception for track deployment errors."""
    pass


def validate_uuid(uuid_string: str, field_name: str) -> str:
    """Validate that a string is a valid UUID."""
    try:
        UUID(uuid_string)
        return uuid_string
    except ValueError:
        raise TrackCopyError(f"Invalid UUID for {field_name}: {uuid_string}")


def get_destination_path(
        base_path: str,
        genome_uuid: str,
        dataset_uuid: str,
        track_name: str,
        extension: str
) -> Path:
    """
    Construct the destination path for a track file.

    Args:
        base_path: Base directory for all track files
        genome_uuid: Genome UUID (must be valid UUID format)
        dataset_uuid: Dataset UUID (must be valid UUID format)
        track_name: Name of the track
        extension: File extension (with or without leading dot)

    Returns:
        Path object for the destination file

    Raises:
        TrackDeploymentError: If UUIDs are invalid
    """
    validate_uuid(genome_uuid, "genome_uuid")
    validate_uuid(dataset_uuid, "dataset_uuid")
    if not extension.startswith('.'):
        extension = f'.{extension}'
    genome_prefix = genome_uuid[:2].lower()
    destination = Path(base_path) / genome_prefix / genome_uuid / f"{dataset_uuid}_{track_name}{extension}"

    return destination


def calculate_checksum(file_path: Path, algorithm: str = 'sha256') -> str:
    """
    Calculate checksum of a file.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hexadecimal checksum string
    """
    hash_func = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def verify_existing_file(source: Path, destination: Path) -> bool:
    """
    Verify if destination file matches source using checksum.

    Args:
        source: Source file path
        destination: Destination file path

    Returns:
        True if files match, False otherwise
    """
    if not destination.exists():
        return False

    try:
        source_checksum = calculate_checksum(source)
        dest_checksum = calculate_checksum(destination)
        return source_checksum == dest_checksum
    except Exception as e:
        logger.warning(f"Checksum verification failed: {e}")
        return False


def copy_track_file(
        source_file: str,
        base_path: str,
        genome_uuid: str,
        dataset_uuid: str,
        track_name: str,
        create_dirs: bool = True,
        overwrite: bool = False,
        skip_existing: bool = False,
        verify_existing: bool = True
) -> tuple[Path, str]:
    """
    Copies a single track file to its destination.

    Args:
        source_file: Path to the source file to copy
        base_path: Base directory for all track files
        genome_uuid: Genome UUID
        dataset_uuid: Dataset UUID
        track_name: Name of the track (without extension)
        create_dirs: Create destination directories if they don't exist
        overwrite: Overwrite destination file if it exists
        skip_existing: Skip files that already exist at destination
        verify_existing: When skip_existing=True, verify with checksum

    Returns:
        Tuple of (Path to the file, status string)
        Status can be: 'copied', 'skipped', 'verified'

    Raises:
        TrackCopyError: If copy fails
    """
    source = Path(source_file)
    if not source.exists():
        raise TrackCopyError(f"Source file does not exist: {source_file}")
    if not source.is_file():
        raise TrackCopyError(f"Source path is not a file: {source_file}")

    extension = source.suffix
    destination = get_destination_path(
        base_path=base_path,
        genome_uuid=genome_uuid,
        dataset_uuid=dataset_uuid,
        track_name=track_name,
        extension=extension
    )

    # Handle existing files
    if destination.exists():
        if skip_existing:
            if verify_existing:
                if verify_existing_file(source, destination):
                    logger.info(f"Verified existing file: {destination}")
                    return destination, 'verified'
                else:
                    logger.warning(f"Checksum mismatch for {destination}, re-copying")
                    # Fall through to copy
            else:
                logger.info(f"Skipped existing file: {destination}")
                return destination, 'skipped'
        elif not overwrite:
            raise TrackCopyError(
                f"Destination file already exists: {destination}. "
                f"Use overwrite=True to replace or skip_existing=True to skip."
            )

    # Create directories if needed
    if create_dirs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {destination.parent}")
    elif not destination.parent.exists():
        raise TrackCopyError(
            f"Destination directory does not exist: {destination.parent}. "
            f"Use create_dirs=True to create it."
        )

    # Copy file
    try:
        shutil.copy2(source, destination)
        logger.info(f"Copied: {source} -> {destination}")
        return destination, 'copied'
    except Exception as e:
        raise TrackCopyError(f"Failed to copy file: {e}")


def copy_from_json(
        json_input: str,
        base_path: str,
        create_dirs: bool = True,
        overwrite: bool = False,
        skip_existing: bool = False,
        verify_existing: bool = True
) -> dict:
    """
    Copy track files based on JSON input.

    JSON format (single file):
        {
            "source_file": "/path/to/file.bb",
            "track_name": "my_track",
            "dataset_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "genome_uuid": "abcd1234-e29b-41d4-a716-446655440000"
        }

    JSON format (multiple files):
        [
            {...},
            {...}
        ]

    Args:
        json_input: JSON string or path to JSON file
        base_path: Base directory for all track files
        create_dirs: Create destination directories if they don't exist
        overwrite: Overwrite destination files if they exist
        skip_existing: Skip files that already exist at destination
        verify_existing: When skip_existing=True, verify with checksum

    Returns:
        Dict with results: {'copied': [...], 'skipped': [...], 'verified': [...], 'failed': [...]}

    Raises:
        TrackCopyError: If JSON parsing fails
    """
    # Try to load as JSON string first, then as file
    try:
        data = json.loads(json_input)
    except json.JSONDecodeError:
        try:
            with open(json_input, 'r') as f:
                data = json.load(f)
        except Exception as e:
            raise TrackCopyError(f"Failed to parse JSON input: {e}")

    # Ensure data is a list
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        raise TrackCopyError("JSON must be a dict or list of dicts")

    results = {
        'copied': [],
        'skipped': [],
        'verified': [],
        'failed': []
    }

    for i, item in enumerate(data):
        # Validate required fields
        required_fields = ['source_file', 'track_name', 'dataset_uuid', 'genome_uuid']
        missing = [f for f in required_fields if f not in item]
        if missing:
            error_msg = f"Item {i}: Missing required fields: {', '.join(missing)}"
            logger.error(error_msg)
            results['failed'].append({'item': item, 'error': error_msg})
            continue

        try:
            copied, status = copy_track_file(
                source_file=item['source_file'],
                base_path=base_path,
                genome_uuid=item['genome_uuid'],
                dataset_uuid=item['dataset_uuid'],
                track_name=item['track_name'],
                create_dirs=create_dirs,
                overwrite=overwrite,
                skip_existing=skip_existing,
                verify_existing=verify_existing
            )
            results[status].append(str(copied))
        except TrackCopyError as e:
            logger.error(f"Failed to copy item {i}: {e}")
            results['failed'].append({'item': item, 'error': str(e)})

    logger.info(
        f"Results: {len(results['copied'])} copied, "
        f"{len(results['verified'])} verified, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['failed'])} failed"
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Deploy track files to genome directory structure'
    )
    parser.add_argument(
        'json_input',
        help='JSON string or path to JSON file with deployment info'
    )
    parser.add_argument(
        '--base-path',
        required=True,
        help='Base directory for track files'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing files'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip files that already exist at destination'
    )
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip checksum verification when using --skip-existing'
    )
    parser.add_argument(
        '--no-create-dirs',
        action='store_true',
        help='Do not create destination directories'
    )
    args = parser.parse_args()

    try:
        results = copy_from_json(
            json_input=args.json_input,
            base_path=args.base_path,
            create_dirs=not args.no_create_dirs,
            overwrite=args.overwrite,
            skip_existing=args.skip_existing,
            verify_existing=not args.no_verify
        )

        print(f"\n✓ Copy completed:")
        print(f"  Copied: {len(results['copied'])} files")
        print(f"  Verified: {len(results['verified'])} files")
        print(f"  Skipped: {len(results['skipped'])} files")
        print(f"  Failed: {len(results['failed'])} files")

        if results['copied']:
            print("\nCopied files:")
            for f in results['copied']:
                print(f"  - {f}")

        if results['failed']:
            print("\nFailed files:")
            for fail in results['failed']:
                print(f"  - {fail['item'].get('source_file', 'unknown')}: {fail['error']}")
            return 1

    except TrackCopyError as e:
        logger.error(f"Copy failed: {e}")
        return 1

    return 0


if __name__ == '__main__':
    import sys

    sys.exit(main())