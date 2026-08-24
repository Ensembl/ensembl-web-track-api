#!/usr/bin/env python3

"""
Create a feature/version_update-style SQLite Track API database from the
    current PostgreSQL Track API schema.

The PostgreSQL schema does not contain dataset/release information. Provide a
track-to-dataset mapping, a genome-to-dataset mapping, or a single dataset UUID
for all tracks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


TRACK_TABLES = (
    "tracks_track_specifications",
    "tracks_track_sources",
    "tracks_specifications",
    "tracks_datasetrelease",
    "tracks_track",
    "tracks_source",
    "tracks_category",
)


def normalize_uuid(value: Any) -> str:
    """Return the hyphenated UUID representation used by this SQLite schema."""
    if value is None:
        raise ValueError("UUID value cannot be null")
    return str(uuid.UUID(str(value)))


def parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def sqlite_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "track"


def specification_name(track: dict[str, Any], files: list[str]) -> str:
    fingerprint_fields = {
        "category_id": track["category_id"],
        "label": track["label"],
        "trigger": track["trigger"],
        "type": track["type"],
        "on_by_default": track["on_by_default"],
        "display_order": track["display_order"],
        "additional_info": track["additional_info"],
        "description": track["description"],
        "settings": track["settings"],
        "files": files,
        "browser": "GenomeBrowser",
    }
    digest = hashlib.sha1(sqlite_json(fingerprint_fields).encode()).hexdigest()[:8]
    base = slugify(track["label"])
    return f"legacy-{base[:33]}-{digest}"[:50]


def load_dataset_map(path: str | None) -> dict[str, tuple[str, str | None]]:
    if not path:
        return {}

    data = json.loads(Path(path).read_text())
    mapping: dict[str, tuple[str, str | None]] = {}

    if isinstance(data, dict):
        for genome_id, dataset_value in data.items():
            release_label = None
            if isinstance(dataset_value, dict):
                dataset_id = dataset_value["dataset_id"]
                release_label = dataset_value.get("release_label")
            else:
                dataset_id = dataset_value
            mapping[normalize_uuid(genome_id)] = (normalize_uuid(dataset_id), release_label)
        return mapping

    if isinstance(data, list):
        for item in data:
            genome_id = normalize_uuid(item["genome_id"])
            dataset_id = normalize_uuid(item["dataset_id"])
            mapping[genome_id] = (dataset_id, item.get("release_label"))
        return mapping

    raise ValueError("--dataset-map must contain a JSON object or list")


def load_track_dataset_map(path: str | None) -> dict[str, tuple[str, str | None]]:
    if not path:
        return {}

    data = json.loads(Path(path).read_text())
    mapping: dict[str, tuple[str, str | None]] = {}

    if isinstance(data, dict):
        for track_id, dataset_value in data.items():
            release_label = None
            if isinstance(dataset_value, dict):
                dataset_id = dataset_value["dataset_id"]
                release_label = dataset_value.get("release_label")
            else:
                dataset_id = dataset_value
            mapping[normalize_uuid(track_id)] = (normalize_uuid(dataset_id), release_label)
        return mapping

    if isinstance(data, list):
        for item in data:
            track_id = normalize_uuid(item["track_id"])
            dataset_id = normalize_uuid(item["dataset_id"])
            mapping[track_id] = (dataset_id, item.get("release_label"))
        return mapping

    raise ValueError("--track-dataset-map must contain a JSON object or list")


def dataset_for_genome(
    genome_id: str,
    default_dataset_id: str | None,
    dataset_map: dict[str, tuple[str, str | None]],
) -> str:
    if genome_id in dataset_map:
        return dataset_map[genome_id][0]
    if default_dataset_id:
        return default_dataset_id
    raise ValueError(
        f"No dataset_id supplied for genome_id {uuid.UUID(genome_id)}. "
        "Use --dataset-id or --dataset-map."
    )


def postgres_dsn(args: argparse.Namespace) -> str:
    if args.pg_dsn:
        return args.pg_dsn

    name = os.getenv("DATABASE_NAME", "postgres")
    user = os.getenv("DATABASE_USER", "postgres")
    password = os.getenv("DATABASE_PASS", "postgres")
    host = os.getenv("DATABASE_HOST", "localhost")
    port = os.getenv("DATABASE_PORT", "5432")
    return f"dbname={name} user={user} password={password} host={host} port={port}"


def create_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        DROP TABLE IF EXISTS tracks_track_sources;
        DROP TABLE IF EXISTS tracks_track_specifications;
        DROP TABLE IF EXISTS tracks_datasetrelease;
        DROP TABLE IF EXISTS tracks_track;
        DROP TABLE IF EXISTS tracks_specifications;
        DROP TABLE IF EXISTS tracks_source;
        DROP TABLE IF EXISTS tracks_category;

        CREATE TABLE tracks_category (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            label varchar(50) NOT NULL,
            track_category_id varchar(50) NOT NULL UNIQUE,
            type varchar(20) NOT NULL
        );

        CREATE TABLE tracks_track (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            track_id char(36) NOT NULL UNIQUE,
            dataset_id char(36) NOT NULL,
            genome_id char(36) NOT NULL,
            datafiles text NOT NULL CHECK ((JSON_VALID(datafiles) OR datafiles IS NULL))
        );

        CREATE TABLE tracks_datasetrelease (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            dataset_id char(36) NOT NULL,
            genome_id char(36) NOT NULL,
            release_label varchar(50) NOT NULL,
            CONSTRAINT unique_dataset_genome_release
                UNIQUE (dataset_id, genome_id, release_label)
        );

        CREATE TABLE tracks_specifications (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            name varchar(50) NOT NULL UNIQUE,
            label varchar(50) NOT NULL,
            trigger text NOT NULL CHECK ((JSON_VALID(trigger) OR trigger IS NULL)),
            type varchar(8) NOT NULL,
            on_by_default bool NOT NULL,
            display_order integer NOT NULL,
            additional_info varchar(50) NOT NULL,
            description text NOT NULL,
            settings text NOT NULL CHECK ((JSON_VALID(settings) OR settings IS NULL)),
            files text NOT NULL CHECK ((JSON_VALID(files) OR files IS NULL)),
            strand varchar(20) NULL,
            browser varchar(20) NOT NULL,
            category_id integer NOT NULL
                REFERENCES tracks_category (id) DEFERRABLE INITIALLY DEFERRED
        );

        CREATE INDEX tracks_specifications_category_id_4069fc3e
            ON tracks_specifications (category_id);

        CREATE TABLE tracks_track_specifications (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            track_id integer NOT NULL
                REFERENCES tracks_track (id) DEFERRABLE INITIALLY DEFERRED,
            specifications_id integer NOT NULL
                REFERENCES tracks_specifications (id) DEFERRABLE INITIALLY DEFERRED
        );

        CREATE UNIQUE INDEX tracks_track_specifications_track_id_specifications_id_91e0c08b_uniq
            ON tracks_track_specifications (track_id, specifications_id);
        CREATE INDEX tracks_track_specifications_track_id_d606db94
            ON tracks_track_specifications (track_id);
        CREATE INDEX tracks_track_specifications_specifications_id_89277052
            ON tracks_track_specifications (specifications_id);

        CREATE TABLE tracks_source (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            name varchar(100) NOT NULL,
            url varchar(200) NOT NULL,
            details varchar(100) NOT NULL DEFAULT '',
            CONSTRAINT unique_source UNIQUE (name, url, details)
        );

        CREATE TABLE tracks_track_sources (
            id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            track_id integer NOT NULL
                REFERENCES tracks_track (id) DEFERRABLE INITIALLY DEFERRED,
            source_id integer NOT NULL
                REFERENCES tracks_source (id) DEFERRABLE INITIALLY DEFERRED
        );

        CREATE UNIQUE INDEX tracks_track_sources_track_id_source_id_uniq
            ON tracks_track_sources (track_id, source_id);
        CREATE INDEX tracks_track_sources_track_id_idx ON tracks_track_sources (track_id);
        CREATE INDEX tracks_track_sources_source_id_idx ON tracks_track_sources (source_id);

        PRAGMA foreign_keys = ON;
        """
    )


def fetch_rows(pg_conn: psycopg2.extensions.connection, sql: str) -> list[dict[str, Any]]:
    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql)
        return [dict(row) for row in cursor.fetchall()]


def postgres_table_exists(pg_conn: psycopg2.extensions.connection, table_name: str) -> bool:
    with pg_conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (table_name,))
        return cursor.fetchone()[0] is not None


def load_sqlite(
    pg_conn: psycopg2.extensions.connection,
    sqlite_conn: sqlite3.Connection,
    default_dataset_id: str | None,
    dataset_map: dict[str, tuple[str, str | None]],
    track_dataset_map: dict[str, tuple[str, str | None]],
    default_release_label: str | None,
) -> dict[str, int]:
    categories = fetch_rows(
        pg_conn,
        """
        SELECT id, label, track_category_id, type
        FROM tracks_category
        ORDER BY id
        """,
    )
    tracks = fetch_rows(
        pg_conn,
        """
        SELECT
            id, track_id, genome_id, category_id, label, trigger, type,
            datafiles, colour, on_by_default, display_order, additional_info,
            description, settings
        FROM tracks_track
        ORDER BY id
        """,
    )
    sources = fetch_rows(
        pg_conn,
        """
        SELECT id, name, url
        FROM tracks_source
        ORDER BY id
        """,
    )

    old_join_table = "tracks_source_track"
    if not postgres_table_exists(pg_conn, old_join_table):
        old_join_table = "tracks_track_sources"

    source_links: list[dict[str, Any]] = []
    if postgres_table_exists(pg_conn, old_join_table):
        source_links = fetch_rows(
            pg_conn,
            f"""
            SELECT track_id, source_id
            FROM {old_join_table}
            ORDER BY id
            """,
        )

    for category in categories:
        sqlite_conn.execute(
            """
            INSERT INTO tracks_category (id, label, track_category_id, type)
            VALUES (?, ?, ?, ?)
            """,
            (
                category["id"],
                category["label"],
                category["track_category_id"],
                category["type"],
            ),
        )

    spec_ids_by_key: dict[str, int] = {}
    track_dataset_release_keys: set[tuple[str, str, str]] = set()

    for track in tracks:
        track["trigger"] = parse_json_field(track["trigger"], [])
        track["datafiles"] = parse_json_field(track["datafiles"], {})
        track["settings"] = parse_json_field(track.get("settings"), {})
        track["additional_info"] = track.get("additional_info") or ""
        track["description"] = track.get("description") or ""
        track["display_order"] = track.get("display_order") or 2000

        files = list(track["datafiles"].keys())
        spec_key = sqlite_json(
            {
                "category_id": track["category_id"],
                "label": track["label"],
                "trigger": track["trigger"],
                "type": track["type"],
                "on_by_default": bool(track["on_by_default"]),
                "display_order": int(track["display_order"]),
                "additional_info": track["additional_info"],
                "description": track["description"],
                "settings": track["settings"],
                "files": files,
                "browser": "GenomeBrowser",
            }
        )

        if spec_key not in spec_ids_by_key:
            cursor = sqlite_conn.execute(
                """
                INSERT INTO tracks_specifications (
                    name, label, category_id, trigger, type, on_by_default,
                    display_order, additional_info, description, settings,
                    files, strand, browser
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    specification_name(track, files),
                    track["label"],
                    track["category_id"],
                    sqlite_json(track["trigger"]),
                    track["type"],
                    int(bool(track["on_by_default"])),
                    int(track["display_order"]),
                    track["additional_info"],
                    track["description"],
                    sqlite_json(track["settings"]),
                    sqlite_json(files),
                    None,
                    "GenomeBrowser",
                ),
            )
            spec_ids_by_key[spec_key] = int(cursor.lastrowid)

        track_id = normalize_uuid(track["track_id"])
        genome_id = normalize_uuid(track["genome_id"])
        dataset_id = track_dataset_map.get(track_id, (None, None))[0]
        if not dataset_id:
            dataset_id = dataset_for_genome(genome_id, default_dataset_id, dataset_map)
        sqlite_conn.execute(
            """
            INSERT INTO tracks_track (id, track_id, dataset_id, genome_id, datafiles)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                track["id"],
                track_id,
                dataset_id,
                genome_id,
                sqlite_json(track["datafiles"]),
            ),
        )
        sqlite_conn.execute(
            """
            INSERT INTO tracks_track_specifications (track_id, specifications_id)
            VALUES (?, ?)
            """,
            (track["id"], spec_ids_by_key[spec_key]),
        )

        release_label = (
            track_dataset_map.get(track_id, ("", None))[1]
            or dataset_map.get(genome_id, ("", None))[1]
            or default_release_label
        )
        if release_label:
            track_dataset_release_keys.add((dataset_id, genome_id, release_label))

    for source in sources:
        sqlite_conn.execute(
            """
            INSERT INTO tracks_source (id, name, url, details)
            VALUES (?, ?, ?, ?)
            """,
            (source["id"], source["name"], source["url"], ""),
        )

    for link in source_links:
        sqlite_conn.execute(
            """
            INSERT OR IGNORE INTO tracks_track_sources (track_id, source_id)
            VALUES (?, ?)
            """,
            (link["track_id"], link["source_id"]),
        )

    for dataset_id, genome_id, release_label in sorted(track_dataset_release_keys):
        sqlite_conn.execute(
            """
            INSERT OR IGNORE INTO tracks_datasetrelease (
                dataset_id, genome_id, release_label
            )
            VALUES (?, ?, ?)
            """,
            (dataset_id, genome_id, release_label),
        )

    return {
        "categories": len(categories),
        "source_links": len(source_links),
        "sources": len(sources),
        "specifications": len(spec_ids_by_key),
        "dataset_releases": len(track_dataset_release_keys),
        "tracks": len(tracks),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert PostgreSQL Track API data to feature/version_update SQLite."
    )
    parser.add_argument(
        "--pg-dsn",
        help=(
            "PostgreSQL DSN. If omitted, DATABASE_NAME, DATABASE_USER, "
            "DATABASE_PASS, DATABASE_HOST and DATABASE_PORT are used."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="SQLite database path to create.",
    )
    parser.add_argument(
        "--dataset-id",
        help="Dataset UUID to assign to every migrated track.",
    )
    parser.add_argument(
        "--dataset-map",
        help=(
            "JSON file mapping genome UUIDs to dataset UUIDs. Values can be "
            "strings or objects with dataset_id and optional release_label."
        ),
    )
    parser.add_argument(
        "--track-dataset-map",
        help=(
            "JSON file mapping track UUIDs to dataset UUIDs. Values can be "
            "strings or objects with dataset_id and optional release_label. "
            "This takes precedence over --dataset-map and --dataset-id."
        ),
    )
    parser.add_argument(
        "--release-label",
        help="Optional release label to insert for every dataset/genome pair.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output SQLite file if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)

    if output.exists() and not args.overwrite:
        print(f"Output already exists: {output}. Use --overwrite to replace it.", file=sys.stderr)
        return 1
    if output.exists():
        output.unlink()

    default_dataset_id = normalize_uuid(args.dataset_id) if args.dataset_id else None
    dataset_map = load_dataset_map(args.dataset_map)
    track_dataset_map = load_track_dataset_map(args.track_dataset_map)

    if not default_dataset_id and not dataset_map and not track_dataset_map:
        print(
            "Provide --track-dataset-map, --dataset-map, or --dataset-id.",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)

    pg_conn = psycopg2.connect(postgres_dsn(args))
    sqlite_conn = sqlite3.connect(output)
    try:
        sqlite_conn.execute("PRAGMA foreign_keys = ON")
        create_sqlite_schema(sqlite_conn)
        counts = load_sqlite(
            pg_conn=pg_conn,
            sqlite_conn=sqlite_conn,
            default_dataset_id=default_dataset_id,
            dataset_map=dataset_map,
            track_dataset_map=track_dataset_map,
            default_release_label=args.release_label,
        )
        sqlite_conn.commit()
    except Exception:
        sqlite_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()

    print(json.dumps({"output": str(output), "counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
