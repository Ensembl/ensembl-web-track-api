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
Unit tests for track_copy module.
"""

import json
import pytest
from pathlib import Path


from src.ensembl.production.tracks.copy_tracks import (
    TrackCopyError,
    validate_uuid,
    get_destination_path,
    calculate_checksum,
    verify_existing_file,
    copy_track_file,
    copy_from_json,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

GENOME_UUID = "abcd1234-e29b-41d4-a716-446655440000"
DATASET_UUID = "550e8400-e29b-41d4-a716-446655440000"
TRACK_NAME = "my_track"
EXTENSION = ".bb"


@pytest.fixture
def source_file(tmp_path) -> Path:
    """Create a temporary source file with known content."""
    f = tmp_path / "my_track.bb"
    f.write_bytes(b"track data content")
    return f


@pytest.fixture
def base_path(tmp_path) -> Path:
    """Return a temporary base path for track deployment."""
    return tmp_path / "tracks"


@pytest.fixture
def valid_json_single(source_file) -> str:
    return json.dumps({
        "source_file": str(source_file),
        "track_name": TRACK_NAME,
        "dataset_uuid": DATASET_UUID,
        "genome_uuid": GENOME_UUID,
    })


@pytest.fixture
def valid_json_multiple(tmp_path, source_file) -> str:
    second_file = tmp_path / "other_track.bb"
    second_file.write_bytes(b"other track data")
    return json.dumps([
        {
            "source_file": str(source_file),
            "track_name": TRACK_NAME,
            "dataset_uuid": DATASET_UUID,
            "genome_uuid": GENOME_UUID,
        },
        {
            "source_file": str(second_file),
            "track_name": "other_track",
            "dataset_uuid": DATASET_UUID,
            "genome_uuid": GENOME_UUID,
        },
    ])


# ── validate_uuid ─────────────────────────────────────────────────────────────

class TestValidateUuid:
    def test_valid_uuid(self):
        result = validate_uuid(GENOME_UUID, "genome_uuid")
        assert result == GENOME_UUID

    def test_invalid_uuid_raises(self):
        with pytest.raises(TrackCopyError, match="Invalid UUID for genome_uuid"):
            validate_uuid("not-a-uuid", "genome_uuid")

    def test_empty_string_raises(self):
        with pytest.raises(TrackCopyError):
            validate_uuid("", "genome_uuid")

    def test_field_name_in_error(self):
        with pytest.raises(TrackCopyError, match="dataset_uuid"):
            validate_uuid("bad", "dataset_uuid")


# ── get_destination_path ──────────────────────────────────────────────────────

class TestGetDestinationPath:
    def test_correct_structure(self):
        dest = get_destination_path("/base", GENOME_UUID, DATASET_UUID, TRACK_NAME, EXTENSION)
        assert dest == Path(f"/base/ab/{GENOME_UUID}/{DATASET_UUID}_{TRACK_NAME}.bb")

    def test_genome_prefix_is_first_two_chars(self):
        dest = get_destination_path("/base", GENOME_UUID, DATASET_UUID, TRACK_NAME, EXTENSION)
        assert dest.parts[-3] == GENOME_UUID[:2].lower()

    def test_extension_without_dot(self):
        dest = get_destination_path("/base", GENOME_UUID, DATASET_UUID, TRACK_NAME, "bb")
        assert dest.suffix == ".bb"

    def test_extension_with_dot(self):
        dest = get_destination_path("/base", GENOME_UUID, DATASET_UUID, TRACK_NAME, ".bb")
        assert dest.suffix == ".bb"

    def test_dataset_and_track_name_concatenated_with_underscore(self):
        dest = get_destination_path("/base", GENOME_UUID, DATASET_UUID, TRACK_NAME, EXTENSION)
        assert dest.name == f"{DATASET_UUID}_{TRACK_NAME}.bb"

    def test_invalid_genome_uuid_raises(self):
        with pytest.raises(TrackCopyError):
            get_destination_path("/base", "bad-uuid", DATASET_UUID, TRACK_NAME, EXTENSION)

    def test_invalid_dataset_uuid_raises(self):
        with pytest.raises(TrackCopyError):
            get_destination_path("/base", GENOME_UUID, "bad-uuid", TRACK_NAME, EXTENSION)

    def test_genome_prefix_is_lowercase(self):
        upper_uuid = GENOME_UUID.upper()
        dest = get_destination_path("/base", upper_uuid, DATASET_UUID, TRACK_NAME, EXTENSION)
        assert dest.parts[-3] == upper_uuid[:2].lower()


# ── calculate_checksum ────────────────────────────────────────────────────────

class TestCalculateChecksum:
    def test_returns_string(self, source_file):
        result = calculate_checksum(source_file)
        assert isinstance(result, str)

    def test_consistent_for_same_file(self, source_file):
        assert calculate_checksum(source_file) == calculate_checksum(source_file)

    def test_different_for_different_content(self, tmp_path):
        f1 = tmp_path / "a.bb"
        f2 = tmp_path / "b.bb"
        f1.write_bytes(b"content a")
        f2.write_bytes(b"content b")
        assert calculate_checksum(f1) != calculate_checksum(f2)

    def test_sha256_length(self, source_file):
        # SHA256 hex digest is always 64 chars
        assert len(calculate_checksum(source_file)) == 64

    def test_md5_algorithm(self, source_file):
        result = calculate_checksum(source_file, algorithm="md5")
        assert len(result) == 32


# ── verify_existing_file ──────────────────────────────────────────────────────

class TestVerifyExistingFile:
    def test_identical_files_return_true(self, tmp_path):
        content = b"some track data"
        src = tmp_path / "src.bb"
        dst = tmp_path / "dst.bb"
        src.write_bytes(content)
        dst.write_bytes(content)
        assert verify_existing_file(src, dst) is True

    def test_different_files_return_false(self, tmp_path):
        src = tmp_path / "src.bb"
        dst = tmp_path / "dst.bb"
        src.write_bytes(b"original")
        dst.write_bytes(b"different")
        assert verify_existing_file(src, dst) is False

    def test_missing_destination_returns_false(self, tmp_path):
        src = tmp_path / "src.bb"
        src.write_bytes(b"data")
        assert verify_existing_file(src, tmp_path / "nonexistent.bb") is False


# ── copy_track_file ───────────────────────────────────────────────────────────

class TestCopyTrackFile:
    def test_successful_copy(self, source_file, base_path):
        dest, status = copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        assert dest.exists()
        assert status == "copied"

    def test_correct_destination_path(self, source_file, base_path):
        dest, _ = copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        assert dest == base_path / "ab" / GENOME_UUID / f"{DATASET_UUID}_{TRACK_NAME}.bb"

    def test_creates_directories_by_default(self, source_file, base_path):
        assert not base_path.exists()
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        assert base_path.exists()

    def test_no_create_dirs_raises_if_missing(self, source_file, base_path):
        with pytest.raises(TrackCopyError, match="Destination directory does not exist"):
            copy_track_file(
                str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME,
                create_dirs=False
            )

    def test_nonexistent_source_raises(self, base_path):
        with pytest.raises(TrackCopyError, match="Source file does not exist"):
            copy_track_file("/nonexistent/file.bb", str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)

    def test_source_is_directory_raises(self, tmp_path, base_path):
        with pytest.raises(TrackCopyError, match="Source path is not a file"):
            copy_track_file(str(tmp_path), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)

    def test_existing_file_raises_without_overwrite(self, source_file, base_path):
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        with pytest.raises(TrackCopyError, match="already exists"):
            copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)

    def test_overwrite_replaces_file(self, source_file, base_path):
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        source_file.write_bytes(b"updated content")
        dest, status = copy_track_file(
            str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME,
            overwrite=True
        )
        assert dest.read_bytes() == b"updated content"
        assert status == "copied"

    def test_skip_existing_returns_skipped(self, source_file, base_path):
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        _, status = copy_track_file(
            str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME,
            skip_existing=True, verify_existing=False
        )
        assert status == "skipped"

    def test_skip_existing_with_matching_checksum_returns_verified(self, source_file, base_path):
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        _, status = copy_track_file(
            str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME,
            skip_existing=True, verify_existing=True
        )
        assert status == "verified"

    def test_skip_existing_with_mismatched_checksum_recopies(self, source_file, base_path):
        copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        source_file.write_bytes(b"new content that differs")
        dest, status = copy_track_file(
            str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME,
            skip_existing=True, verify_existing=True
        )
        assert status == "copied"
        assert dest.read_bytes() == b"new content that differs"

    def test_file_content_is_preserved(self, source_file, base_path):
        original_content = source_file.read_bytes()
        dest, _ = copy_track_file(str(source_file), str(base_path), GENOME_UUID, DATASET_UUID, TRACK_NAME)
        assert dest.read_bytes() == original_content


# ── copy_from_json ────────────────────────────────────────────────────────────

class TestCopyFromJson:
    def test_single_dict_json(self, valid_json_single, base_path):
        results = copy_from_json(valid_json_single, str(base_path))
        assert len(results["copied"]) == 1
        assert len(results["failed"]) == 0

    def test_list_json(self, valid_json_multiple, base_path):
        results = copy_from_json(valid_json_multiple, str(base_path))
        assert len(results["copied"]) == 2
        assert len(results["failed"]) == 0

    def test_json_file_input(self, tmp_path, valid_json_single, base_path):
        json_file = tmp_path / "input.json"
        json_file.write_text(valid_json_single)
        results = copy_from_json(str(json_file), str(base_path))
        assert len(results["copied"]) == 1

    def test_missing_required_field_goes_to_failed(self, base_path):
        bad_json = json.dumps({"source_file": "/some/file.bb", "track_name": "x"})
        results = copy_from_json(bad_json, str(base_path))
        assert len(results["failed"]) == 1
        assert "dataset_uuid" in results["failed"][0]["error"]

    def test_invalid_json_raises(self, base_path):
        with pytest.raises(TrackCopyError, match="Failed to parse JSON"):
            copy_from_json("not json at all", str(base_path))

    def test_partial_failure_continues(self, tmp_path, base_path):
        """One bad file should not prevent others from being copied."""
        good_file = tmp_path / "good.bb"
        good_file.write_bytes(b"good data")
        data = json.dumps([
            {
                "source_file": "/nonexistent/bad.bb",
                "track_name": "bad_track",
                "dataset_uuid": DATASET_UUID,
                "genome_uuid": GENOME_UUID,
            },
            {
                "source_file": str(good_file),
                "track_name": "good_track",
                "dataset_uuid": DATASET_UUID,
                "genome_uuid": GENOME_UUID,
            },
        ])
        results = copy_from_json(data, str(base_path))
        assert len(results["copied"]) == 1
        assert len(results["failed"]) == 1

    def test_skip_existing_in_copy_from_json(self, valid_json_single, base_path):
        copy_from_json(valid_json_single, str(base_path))
        results = copy_from_json(valid_json_single, str(base_path), skip_existing=True, verify_existing=False)
        assert len(results["skipped"]) == 1
        assert len(results["copied"]) == 0

    def test_verified_existing_in_copy_from_json(self, valid_json_single, base_path):
        copy_from_json(valid_json_single, str(base_path))
        results = copy_from_json(valid_json_single, str(base_path), skip_existing=True, verify_existing=True)
        assert len(results["verified"]) == 1

    def test_invalid_list_type_raises(self, base_path):
        with pytest.raises(TrackCopyError, match="JSON must be a dict or list"):
            copy_from_json(json.dumps("just a string"), str(base_path))

    def test_results_dict_has_all_keys(self, valid_json_single, base_path):
        results = copy_from_json(valid_json_single, str(base_path))
        assert set(results.keys()) == {"copied", "skipped", "verified", "failed"}