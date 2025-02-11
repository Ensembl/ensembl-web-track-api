#!/usr/bin/env python3

"""
Script for submitting track records to Track API. In a nutshell, the script:
1) Fills in track templates (loaded from yaml files) from CLI params, CSV files and filenames in TRACK_DATA_DIR
2) Submits the result as JSON payloads to TRACK_API_URL
See the params below for more granulated track loading (specific release, genomes, tracks etc.)
"""

import argparse
import csv
import glob
import os.path
import requests
from typing_extensions import NotRequired, TypedDict
from uuid import UUID
import yaml

from . import create_gene_csv

# Datamodels for static typing (runtime checks done by Track API)
class TrackData(TypedDict):
    category: str
    genome_id: str
    label: str
    datafiles: dict[str, str]
    description: str
    display_order: int
    on_by_default: bool
    settings: NotRequired[dict]
    sources: NotRequired[list[dict]]
    trigger: list[str]
    type: str


class CSVRow(TypedDict):
    desc: str
    name: str
    sources: list[str]
    urls: list[str]


CSVData = dict[str, CSVRow]
CSVCollection = dict[str, CSVData]

args = argparse.Namespace()
template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
GENE_CSV_FILE = f"{template_dir}/gene-track-desc.csv"
VARIANT_CSV_FILE = f"{template_dir}/variant-track-desc.csv"
EXT = ".yaml"
templates = [
    os.path.basename(f).replace(EXT, "") for f in glob.glob(f"{template_dir}/*{EXT}")
]
track_api_url = os.environ.get("TRACK_API_URL", "")
data_dir = os.environ.get("TRACK_DATA_DIR", "")
csv_data: CSVCollection = {}
logfile = None


def fail(msg):
    if msg:
        print(msg)
    if logfile:
        print(msg, file=logfile)
        logfile.close()
    exit(1)


def process_input_parameters():
    global args, track_api_url, data_dir
    parser = argparse.ArgumentParser(
        description="Submit tracks to Track API based on input datafiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Required environment variables: 
  - TRACK_API_URL: Track API endpoint (e.g. https://dev-2020.ensembl.org/api/tracks)
    Can be omitted for dry-run mode (-d)
  - TRACK_DATA_DIR: Directory containing track datafiles (in genome ID subdirectories)
    Can be omitted if a track list is specified with -g and -f or -t

Examples:
  - Submit tracks for all datafiles in TRACK_DATA_DIR (skipping existing tracks): submit_tracks.py
  - Same as above, but limit to genomes in release 5: submit_tracks.py --release 5
  - Resubmit all tracks for dog and pig: submit_tracks.py -o -g 2284d28a-2cf7-41f0-bed6-0982601f7888 a7335667-93e7-11ec-a39d-005056b38ce3
  - Submit gene tracks for dog (TRACK_DATA_DIR not needed): submit_tracks.py -t transcripts -g 2284d28a-2cf7-41f0-bed6-0982601f7888
  """,
    )
    parser.add_argument(
        "-f",
        "--file",
        nargs="*",
        metavar="FILENAME",
        help="limit to specific track datafiles",
    )
    parser.add_argument(
        "-t",
        "--template",
        nargs="*",
        metavar="TEMPLATE",
        help="limit to specific track templates (types)",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        nargs="*",
        metavar="TEMPLATE",
        help="exclude specific track templates (types)",
    )
    parser.add_argument(
        "-c",
        "--continue",
        metavar="GENOME_ID",
        help="continue (resume) track loading from a specific genome ID)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-g",
        "--genome",
        nargs="*",
        metavar="GENOME_ID",
        help="limit to specific genomes",
    )
    group.add_argument(
        "-r",
        "--release",
        metavar="RELEASE",
        type=int,
        help="load tracks for a specific release number",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="do not submit tracks, just print the payload",
    )
    group.add_argument(
        "-o", "--overwrite", action="store_true", help="overwrite (all) existing tracks"
    )
    group.add_argument(
        "-l",
        "--logfile",
        metavar="FILENAME",
        default="track_submission.log",
        help="log progress to a file (use '' for no logfile, default: %(default)s)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress status messages"
    )

    parser.parse_args(namespace=args)
    if not track_api_url and not args.dry_run:
        fail("Error: TRACK_API_URL environment variable not set")
    if not data_dir and not (args.genome and (args.file or args.template)):
        fail("Error: TRACK_DATA_DIR environment variable not set")
    if args.template:
        args.template = [t.replace(EXT, "") for t in args.template]


# Print messages in verbose mode
def log(msg: object) -> None:
    if not args.quiet:
        print(msg)
    if logfile:
        print(msg, file=logfile)


# Limit tracks to those specified in command-line args
def filter_templates() -> None:
    global templates
    if args.template:
        templates = [
            t for t in templates if any(t.startswith(i) for i in args.template)
        ]
    if args.exclude:
        templates = [
            t for t in templates if not any(t.startswith(e) for e in args.exclude)
        ]


# Read species-specific track template fields from CSV file
def parse_csv(path: str) -> CSVData:
    data: CSVData = {}
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            for line in reader:
                data[line["Genome_UUID"]] = {
                    "desc": line["Description"],
                    "name": line["Track_name"] if "Track_name" in line else "",
                    "sources": line["Source_name"].split(","),
                    "urls": line["Source_URL"].split(","),
                }
    except FileNotFoundError:
        fail(f"Error: track description CSV file not found in {path}")
    except KeyError as e:
        fail(f"Error: unexpected CSV format in {path} ({e})")
    return data


# Track loading process:
# 1) Loop through all track datafiles in the data directory
def process_data_dir() -> None:
    if not os.path.isdir(data_dir):
        fail(f"Error: data directory {data_dir} not found")
    subdirs = os.listdir(data_dir)
    i = 0
    total = len(args.genome or subdirs)
    for subdir in subdirs:
        if not os.path.isdir(f"{data_dir}/{subdir}"):
            continue
        try:
            UUID(subdir, version=4)
        except ValueError:
            log(f"Skipping non-genome directory {subdir}")
            continue
        if args.genome and subdir not in args.genome:
            continue
        i += 1
        if args.resume:
            if subdir != args.resume:
                log(f"Skipping genome {subdir} ({i}/{total})")
                continue
            else:
                args.resume = None
        log(f"Processing genome {subdir} ({i}/{total})")
        if args.overwrite:  # delete existing tracks first
            delete_tracks(subdir)
        for file in os.listdir(f"{data_dir}/{subdir}"):
            if file.endswith(".bb") or file.endswith(".bw"):
                match_template(subdir, file)


# 1b) ...or use a list of tracks specified in command-line args
def process_track_list() -> None:
    files = args.template or args.file
    total = len(args.genome)
    for i, genome_id in enumerate(args.genome):
        if args.resume:
            if genome_id != args.resume:
                log(f"Skipping genome {genome_id} ({i+1}/{total})")
                continue
            else:
                args.resume = None
        log(f"Processing genome {genome_id} ({i+1}/{total})")
        if args.overwrite:  # delete existing tracks first
            delete_tracks(genome_id)
        for filename in files:
            match_template(genome_id, filename)


# 2) Load the track payload template(s) for each datafile
def match_template(genome_id: str, datafile: str) -> None:
    if args.file and not args.template and datafile not in args.file:
        return
    filename = os.path.splitext(datafile)[0]
    # skip variant focus tracks and redundant bigwig files
    if filename == "variant-details" or filename.endswith("-summary"):
        return
    # exact datafile=>template name match
    if filename in templates:
        apply_template(genome_id, filename)
        return
    # partial name match (multiple tracks per datafile or vice versa)
    multimatch = False
    for template_name in templates:
        # multiple templates (tracks) per datafile (e.g. transcripts.bb)
        if template_name.startswith(filename):
            apply_template(genome_id, template_name)
            multimatch = True
        # single template matches many datafiles (e.g. repeats.repeatmask*.bb)
        if not multimatch and filename.startswith(template_name):
            apply_template(genome_id, template_name, datafile)
            return
    # unexpected datafile
    if not multimatch:
        log(f"Warning: No track template found for {datafile}")


# 3) Fill in the template (update variable fields)
def apply_template(genome_id: str, template_name: str, datafile: str = "") -> None:
    with open(f"{template_dir}/{template_name}{EXT}", "r") as template_file:
        track_data: TrackData = yaml.safe_load(template_file)
    track_data["genome_id"] = genome_id  # always updated
    # update datafile field (when a template matches multiple datafiles)
    if datafile:
        for key, value in track_data["datafiles"].items():
            # derive bw filename for bb/bw datafile pairs
            if key.endswith("summary") and value:
                nameroot = datafile[: datafile.rfind("-")]
                track_data["datafiles"][key] = f"{nameroot}-summary.bw"
            else:
                track_data["datafiles"][key] = datafile
    # udpate species-specific fields (gene & variation tracks)
    if template_name.startswith("transcripts") or template_name.startswith("variant"):
        track_type = "gene" if template_name.startswith("transcripts") else "variant"
        if genome_id in csv_data[track_type]:
            row = csv_data[track_type][genome_id]
            if row["name"]:
                track_data["label"] = row["name"]
            if row["desc"]:
                if track_type == "gene":
                    if row["sources"][0]:
                        track_data[
                            "description"
                        ] += f"\nGenes {'annotated by' if row['desc']=='Annotated' else 'imported from'}  {row['sources'][0]}."
                else:
                    track_data["description"] = row["desc"]
            if row["sources"][0] and len(row["sources"]) == len(row["urls"]):
                if "sources" not in track_data:
                    track_data["sources"] = []
                for i, source_name in enumerate(row["sources"]):
                    if not source_name or not row["urls"][i]:
                        continue
                    track_data["sources"].append(
                        {"name": source_name, "url": row["urls"][i]}
                    )
        elif track_type == "gene":
            log("Warning: Missing gene track descriptions.")
    # submit the track payload
    submit_track(track_data)


# 4) Submit the track payload to Track API
def submit_track(track_data: TrackData, second_try: bool = False) -> None:
    log(f"Submitting track: {track_data['label']}")
    if args.dry_run:
        log(track_data)
        return

    try:
        request = requests.post(f"{track_api_url}/track", json=track_data)
    except requests.exceptions.ConnectTimeout:
        if second_try:
            fail("Error: No response from Track API.")
        else:
            log("Connection timed out. Retrying...")
            submit_track(track_data, True)

    msg = request.content.decode()
    if request.status_code == 201:
        log(msg)  # expected response: {"track_id": "some-uuid"}
    elif request.status_code == 400 and "unique" in msg:
        log("Track already exists, skipping.")
    else:
        fail(
            f"Error submitting track ({request.status_code}): {msg[:100]}\nTrack payload: {track_data}"
        )


# Do track cleanup in overwrite mode
def delete_tracks(genome_id: str) -> None:
    request = requests.delete(f"{track_api_url}/track_categories/{genome_id}")
    if request.status_code != 204 and request.status_code != 404:
        log(f"Could not delete tracks for {genome_id}: {request.content.decode()}")


if __name__ == "__main__":
    # setup
    process_input_parameters()
    filter_templates()

    # dump gene track metadata to CSV
    if args.release:
        create_gene_csv.OUTFILENAME = GENE_CSV_FILE
        create_gene_csv.RELEASE_ID = args.release
        create_gene_csv.main()

    # read species-specific track info from CSV
    csv_data["gene"] = parse_csv(GENE_CSV_FILE)
    csv_data["variant"] = parse_csv(VARIANT_CSV_FILE)
    # limit to genomes in specified release
    if args.release:
        args.genome = csv_data["gene"].keys()

    if args.logfile:
        try:
            logfile = open(args.logfile, "w")
        except IOError as e:
            log(f"Warning: cannot open logfile {args.logfile}: {e}")

    # run track loading
    if track_api_url:
        log(f"Submitting tracks to {track_api_url}")
    if data_dir:
        process_data_dir()
    elif args.genome and (args.file or args.template):
        process_track_list()
    else:
        fail(
            "Please provide either a data directory or a list of tracks (genomes+template names) to be loaded."
        )
    if logfile:
        logfile.close()
