#!/usr/bin/env python3

"""
Build a feature/version_update-style SQLite Track API database directly from:

* a DuckDB copy of ensembl_genome_metadata
* Track API YAML templates
* genome-browser track file directories named by genome UUID

This mirrors the production track_api_loading.py matching/enrichment logic, but
writes the SQLite schema directly instead of POSTing to a running Track API.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

try:
    import duckdb
except ImportError:  # pragma: no cover - depends on local environment
    duckdb = None


TRACK_ID_NAMESPACE = uuid.UUID("9bc37713-89eb-44fd-9d71-0cdbbef394c0")


def normalize_uuid(value: Any) -> str:
    return str(uuid.UUID(str(value)))


def uuid_for_track(genome_id: str, template_name: str, datafiles: dict[str, str]) -> str:
    fingerprint = json.dumps(
        {
            "genome_id": normalize_uuid(genome_id),
            "template_name": template_name,
            "datafiles": datafiles,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(TRACK_ID_NAMESPACE, fingerprint))


def sqlite_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


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


def load_templates(template_dir: Path) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    for path in sorted(template_dir.glob("*.yaml")):
        with path.open() as handle:
            templates[path.stem] = yaml.safe_load(handle)
    return templates


def matching_templates(
    filename: str,
    templates: dict[str, dict[str, Any]],
) -> list[tuple[str, str | None]]:
    stem = Path(filename).stem
    if stem == "variant-details" or stem.endswith("-summary"):
        return []
    if stem in templates:
        return [(stem, filename)]

    matches: list[tuple[str, str | None]] = []
    for template_name in templates:
        if template_name.startswith(stem):
            matches.append((template_name, filename))
        if not matches and stem.startswith(template_name):
            return [(template_name, filename)]
    return matches


def update_datafiles(track_payload: dict[str, Any], datafile: str) -> None:
    for key, value in track_payload["datafiles"].items():
        if not value:
            continue
        if key.endswith("summary"):
            nameroot = datafile[: datafile.rfind("-")]
            track_payload["datafiles"][key] = f"{nameroot}-summary.bw"
        else:
            track_payload["datafiles"][key] = datafile


def fetch_gene_metadata(
    con: duckdb.DuckDBPyConnection,
    dataset_type: str,
    release_label: str | None,
    release_type: str | None,
) -> dict[str, dict[str, Any]]:
    conditions = ["dt.name = ?"]
    params: list[Any] = [dataset_type]
    if release_label:
        conditions.append("er.label = ?")
        params.append(release_label)
    if release_type:
        conditions.append("er.release_type = ?")
        params.append(release_type)

    rows = con.execute(
        f"""
        SELECT
            g.genome_uuid,
            d.dataset_uuid,
            er.label AS release_label,
            er.release_date,
            gd.is_current,
            a.name AS attribute_name,
            da.value AS attribute_value
        FROM dataset d
        JOIN dataset_type dt ON dt.dataset_type_id = d.dataset_type_id
        JOIN genome_dataset gd ON gd.dataset_id = d.dataset_id
        JOIN genome g ON g.genome_id = gd.genome_id
        LEFT JOIN ensembl_release er ON er.release_id = gd.release_id
        LEFT JOIN dataset_attribute da ON da.dataset_id = d.dataset_id
        LEFT JOIN attribute a ON a.attribute_id = da.attribute_id
        WHERE {" AND ".join(conditions)}
          AND d.status = 'Released'
        ORDER BY g.genome_uuid, er.release_date DESC NULLS LAST, gd.is_current DESC
        """,
        params,
    ).fetchall()

    metadata: dict[str, dict[str, Any]] = {}
    for (
        genome_uuid,
        dataset_uuid,
        row_release_label,
        release_date,
        is_current,
        attribute_name,
        attribute_value,
    ) in rows:
        genome_key = normalize_uuid(genome_uuid)
        row = metadata.setdefault(
            genome_key,
            {
                "dataset_id": normalize_uuid(dataset_uuid),
                "release_label": row_release_label or str(release_date),
                "is_current": bool(is_current),
                "attributes": {},
            },
        )
        if attribute_name and attribute_value:
            row["attributes"][attribute_name] = attribute_value

    return metadata


def apply_gene_metadata(payload: dict[str, Any], metadata: dict[str, Any]) -> None:
    attrs = metadata.get("attributes", {})
    provider_name = attrs.get("genebuild.provider_name")
    provider_url = attrs.get("genebuild.provider_url")

    if provider_name == "Ensembl":
        postfix = " Genes annotated by Ensembl."
    elif provider_name:
        postfix = f" Genes imported from {provider_name}."
    else:
        postfix = " Genes annotated by Ensembl."

    payload["description"] = f"{payload.get('description', '')}{postfix}"
    if provider_name and provider_url:
        payload.setdefault("sources", [])
        payload["sources"].append({"name": provider_name, "url": provider_url})


def load_handover(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open() as handle:
        return json.load(handle)


class SQLiteWriter:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.category_ids: dict[str, int] = {}
        self.specification_ids: dict[str, int] = {}
        self.source_ids: dict[tuple[str, str, str], int] = {}

    def category_id(self, category: dict[str, Any]) -> int:
        track_category_id = category["track_category_id"]
        if track_category_id in self.category_ids:
            return self.category_ids[track_category_id]

        cursor = self.conn.execute(
            """
            INSERT INTO tracks_category (label, track_category_id, type)
            VALUES (?, ?, ?)
            ON CONFLICT(track_category_id) DO UPDATE SET
                label = excluded.label,
                type = excluded.type
            RETURNING id
            """,
            (category["label"], track_category_id, category.get("type", "Genomic")),
        )
        category_id = int(cursor.fetchone()[0])
        self.category_ids[track_category_id] = category_id
        return category_id

    def specification_id(self, template_name: str, payload: dict[str, Any]) -> int:
        if template_name in self.specification_ids:
            return self.specification_ids[template_name]

        category_id = self.category_id(payload["category"])
        cursor = self.conn.execute(
            """
            INSERT INTO tracks_specifications (
                name, label, category_id, trigger, type, on_by_default,
                display_order, additional_info, description, settings,
                files, strand, browser
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                template_name[:50],
                payload["label"],
                category_id,
                sqlite_json(payload["trigger"]),
                payload["type"],
                int(bool(payload.get("on_by_default", False))),
                int(payload.get("display_order", 2000)),
                payload.get("additional_info", ""),
                payload.get("description", ""),
                sqlite_json(payload.get("settings", {})),
                sqlite_json(list(payload["datafiles"].keys())),
                payload.get("strand"),
                payload.get("browser", "GenomeBrowser"),
            ),
        )
        specification_id = int(cursor.fetchone()[0])
        self.specification_ids[template_name] = specification_id
        return specification_id

    def source_id(self, source: dict[str, Any]) -> int:
        key = (source["name"], source["url"], source.get("details", ""))
        if key in self.source_ids:
            return self.source_ids[key]
        cursor = self.conn.execute(
            """
            INSERT INTO tracks_source (name, url, details)
            VALUES (?, ?, ?)
            ON CONFLICT(name, url, details) DO UPDATE SET
                name = excluded.name
            RETURNING id
            """,
            key,
        )
        source_id = int(cursor.fetchone()[0])
        self.source_ids[key] = source_id
        return source_id

    def add_track(
        self,
        genome_id: str,
        dataset_id: str,
        release_label: str,
        template_name: str,
        payload: dict[str, Any],
    ) -> None:
        specification_id = self.specification_id(template_name, payload)
        track_id = uuid_for_track(genome_id, template_name, payload["datafiles"])

        cursor = self.conn.execute(
            """
            INSERT INTO tracks_track (track_id, dataset_id, genome_id, datafiles)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                dataset_id = excluded.dataset_id,
                genome_id = excluded.genome_id,
                datafiles = excluded.datafiles
            RETURNING id
            """,
            (
                track_id,
                normalize_uuid(dataset_id),
                normalize_uuid(genome_id),
                sqlite_json(payload["datafiles"]),
            ),
        )
        sqlite_track_id = int(cursor.fetchone()[0])
        self.conn.execute(
            """
            INSERT OR IGNORE INTO tracks_track_specifications
                (track_id, specifications_id)
            VALUES (?, ?)
            """,
            (sqlite_track_id, specification_id),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO tracks_datasetrelease
                (dataset_id, genome_id, release_label)
            VALUES (?, ?, ?)
            """,
            (normalize_uuid(dataset_id), normalize_uuid(genome_id), release_label),
        )

        for source in payload.get("sources", []):
            source_id = self.source_id(source)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO tracks_track_sources (track_id, source_id)
                VALUES (?, ?)
                """,
                (sqlite_track_id, source_id),
            )


def build_sqlite(args: argparse.Namespace) -> dict[str, int]:
    if duckdb is None:
        raise RuntimeError(
            "The duckdb Python package is required. Install it with: "
            "python -m pip install duckdb"
        )

    templates = load_templates(Path(args.track_templates_dir))
    handover = load_handover(args.handover_json)
    duck = duckdb.connect(args.duck_meta_db, read_only=True)
    gene_metadata = fetch_gene_metadata(
        duck,
        dataset_type=args.dataset_type,
        release_label=args.release_label,
        release_type=args.release_type,
    )

    sqlite_conn = sqlite3.connect(args.output)
    writer = SQLiteWriter(sqlite_conn)
    counts = {"genomes": 0, "tracks": 0, "skipped_missing_metadata": 0}

    try:
        create_sqlite_schema(sqlite_conn)
        file_root = Path(args.file_path)
        genome_dirs = [
            path
            for path in sorted(file_root.iterdir())
            if path.is_dir()
            and (not args.genome_uuid or path.name in args.genome_uuid)
        ]
        for genome_dir in genome_dirs:
            genome_id = normalize_uuid(genome_dir.name)
            metadata = gene_metadata.get(genome_id)
            if not metadata:
                counts["skipped_missing_metadata"] += 1
                continue
            counts["genomes"] += 1
            for path in sorted(genome_dir.iterdir()):
                if not path.is_file() or path.suffix not in {".bb", ".bw"}:
                    continue
                for template_name, datafile_override in matching_templates(path.name, templates):
                    payload = json.loads(json.dumps(templates[template_name]))
                    payload["genome_id"] = str(uuid.UUID(genome_id))
                    if datafile_override:
                        update_datafiles(payload, datafile_override)
                    if payload.get("type") == "gene":
                        apply_gene_metadata(payload, metadata)
                    if payload.get("type") == "variant" and genome_id in handover:
                        variant_data = handover.get(genome_id, {})
                        if isinstance(variant_data, dict):
                            payload.update(variant_data)
                    writer.add_track(
                        genome_id=genome_id,
                        dataset_id=metadata["dataset_id"],
                        release_label=metadata["release_label"],
                        template_name=template_name,
                        payload=payload,
                    )
                    counts["tracks"] += 1
        sqlite_conn.commit()
    except Exception:
        sqlite_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        duck.close()

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SQLite Track API DB from DuckDB metadata and track files."
    )
    parser.add_argument("--duck-meta-db", required=True, help="Path to duck_meta.db")
    parser.add_argument("--file-path", required=True, help="Genome-browser files directory")
    parser.add_argument("--track-templates-dir", required=True, help="Track YAML templates directory")
    parser.add_argument("--output", required=True, help="SQLite database path to create")
    parser.add_argument("--genome-uuid", nargs="*", default=[], help="Optional genome UUID filter")
    parser.add_argument("--dataset-type", default="genebuild", help="Metadata dataset type")
    parser.add_argument("--release-label", help="Optional ensembl_release.label filter")
    parser.add_argument("--release-type", default="partial", help="Optional release_type filter")
    parser.add_argument("--handover-json", help="Optional variant handover JSON")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output DB")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    if output.exists() and not args.overwrite:
        print(f"Output already exists: {output}. Use --overwrite.", file=sys.stderr)
        return 1
    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    counts = build_sqlite(args)
    print(json.dumps({"output": str(output), "counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
