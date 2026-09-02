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
Variation Orchestration. This script will be moved entirely to airflow once airflow 3.0 and the api is ready.
- Takes an input json,
- Validates its fields
- Runs Datachecks
- Creates a metadata entry, while tracking the dataset uuid.
- Copies and renames the tracks while adding the new location to metadata source
- Loads the track into the track API

We want this modular so we can hopefully move it to any orchestration/pipeline manager and swap them if needed.
"""
import argparse

#Step 1: Input Json

#Step 2: Validation

#Step 3: Run Datachecks

#Step 4: Metadata dataset factory

#Step 5: Copy/rename











def main():
    parser = argparse.ArgumentParser(
        description='Deploy track files to genome directory structure'
    )
    parser.add_argument(
        'json_input',
        help='JSON string or path to JSON file with track info'
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