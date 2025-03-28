#!/usr/bin/env python3

"""
Script for submitting track records to Track API. In a nutshell, the script:
1) Fills in track templates based on CLI params, metadata (from db & csv), and filenames in a data dir
2) Submits the resulting track records as JSON payloads to Track API REST endpoint
Only required parameter is release nr. See below for additional options.
"""

import argparse
import csv
import glob
import os.path
import requests
from typing_extensions import NotRequired, TypedDict
from uuid import UUID
import yaml

from get_gene_track_desc import main  as get_gene_desc

# Datamodel for track payloads
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

# Datamodel for track descriptions
class DescData(TypedDict):
    description: str
    source_names: list[str]
    source_urls: list[str]
    track_name: NotRequired[str]

Descriptions = dict[str, DescData]
DescCollection = dict[str, Descriptions]

# Global variables / constants
dir_root = "/nfs/public/ro/enswbsites_codon/newsite"
dir_tail = "genome_browser/8"
ENV = {
    "dev": {
        "data_dir": f"{dir_root}/dev/{dir_tail}",
        "track_api_url": "https://dev-2020.ensembl.org"
    },
    "staging": {
        "data_dir": f"{dir_root}/staging/{dir_tail}",
        "track_api_url": "https://staging-2020.ensembl.org"
    },
    "prod": {
        "data_dir": f"{dir_root}/live/{dir_tail}",
        "track_api_url": "https://beta.ensembl.org"
    },
}

args = argparse.Namespace()
template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
VARIANT_CSV_FILE = f"{template_dir}/variant-track-desc.csv"
EXT = ".yaml"
templates = [
    os.path.basename(f).replace(EXT, "") for f in glob.glob(f"{template_dir}/*{EXT}")
]
data_dir = ""
track_api_url = ""
metadata: DescCollection = {"gene":{}, "variant":{}}
logfile = None


# Helper functions
def fail(msg):
    if msg:
        print(msg)
    if logfile:
        print(msg, file=logfile)
        logfile.close()
    exit(1)


def process_input_parameters():
    global args, track_api_url, data_dir
    prog = os.path.basename(__file__)
    envs = list(ENV.keys())
    parser = argparse.ArgumentParser(
        description="Submit Genome Browser tracks to Track API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Submits track records (based on yaml templates) to Track API endpoint.
For input, it needs a list of genome UUIDs (derived from --release param), 
list of track types, and the target endpoint URL (both derived from --env param).
Optional environment variables (overrides defaults from --env): 
  - TRACK_API_URL: Track API endpoint URL. Not used in dry-run mode (-d).
  - TRACK_DATA_DIR: Directory containing track datafiles.
    Not used when the track types are specified with -f or -t.

Examples:
  - Submit all tracks for release beta-5 to dev: {prog} --release 5
  - Resubmit all tracks for dog and pig: {prog} -r 5 -o -g 2284d28a-2cf7-41f0-bed6-0982601f7888 a7335667-93e7-11ec-a39d-005056b38ce3
  - Submit gene tracks for dog (data dir not used): {prog} -r 5 -t transcripts -g 2284d28a-2cf7-41f0-bed6-0982601f7888
  """,
    )
    parser.add_argument(
        "-r",
        "--release",
        metavar="RELEASE",
        type=int,
        required=True,
        help="load tracks for a specific release number",
    )
    parser.add_argument(
        "-e",
        "--env",
        choices=envs,
        default=envs[0], #dev
        const=envs[0],
        nargs="?",
        type=str,
        help="source/target environment (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="*",
        action="extend",
        metavar="FILENAMES",
        help="limit to specific track datafiles",
    )
    parser.add_argument(
        "-g",
        "--genomes",
        nargs="*",
        action="extend",
        metavar="GENOME_IDS",
        help="limit to specific genome UUIDs",
    )
    parser.add_argument(
        "-t",
        "--templates",
        nargs="*",
        action="extend",
        help="limit to specific track types (templates)",
    )
    parser.add_argument(
        "-c",
        "--continue",
        dest="resume",
        metavar="GENOME_ID",
        help="resume track loading process from a specific genome ID",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="do not submit tracks, just print the payloads",
    )
    parser.add_argument(
        "-l",
        "--logfile",
        metavar="FILENAME",
        default="track_submission.log",
        help="log progress to a file (use '' for no logfile, default: %(default)s)",
    )
    parser.add_argument(
        "-o", "--overwrite", action="store_true", help="overwrite (all) existing tracks"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress status messages"
    )

    parser.parse_args(namespace=args)
    if not args.release:
        fail("Error: Please provide a release number.")
    if args.env not in ENV:
        fail(f"Error: Invalid environment name (expected: {' | '.join(envs)}).")
    track_api_url = os.getenv("TRACK_API_URL", ENV[args.env]["track_api_url"])
    data_dir = os.getenv("TRACK_DATA_DIR", ENV[args.env]["data_dir"])
    if args.templates:
        args.templates = [t.replace(EXT, "") for t in args.templates]


# Print messages in verbose mode
def log(msg: object) -> None:
    if not args.quiet:
        print(msg)
    if logfile:
        print(msg, file=logfile)

# Read species-specific track descriptions from CSV file
def parse_csv(path: str) -> Descriptions:
    data: Descriptions = {}
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            for line in reader:
                data[line["Genome_UUID"]] = {
                    "description": line["Description"],
                    "track_name": line["Track_name"] if "Track_name" in line else "",
                    "source_names": line["Source_name"].split(","),
                    "source_urls": line["Source_URL"].split(","),
                }
    except FileNotFoundError:
        fail(f"Error: track description CSV file not found in {path}")
    except KeyError as e:
        fail(f"Error: unexpected CSV format in {path} ({e})")
    return data


# Track loading process:
# 1) Option A: loop through the track datafiles in the data directory
def process_data_dir() -> None:
    """
    Processes the track datafiles direcotry to compose a list of tracks to be submitted for each genome.
    Datadir is expected to have subdirectories named after genome UUIDs, containing track datafiles.
    Forwards the list of genomes and datafiles to the `match_template` function for further processing.
    """

    if not os.path.isdir(data_dir):
        fail(f"Error: data directory {data_dir} not found")
    subdirs = os.listdir(data_dir)
    i = 0
    total = len(args.genomes or subdirs)
    if args.genomes:
        missing_genomes = [genome for genome in args.genomes if genome not in subdirs]
        if missing_genomes:
            fail(f"Error: Genome(s) missing in data directory: {', '.join(missing_genomes)}")
    for subdir in subdirs:
        if not os.path.isdir(f"{data_dir}/{subdir}"):
            continue
        try:
            UUID(subdir, version=4)
        except ValueError:
            log(f"Skipping non-genome directory {subdir}")
            continue
        if args.genomes and subdir not in args.genomes:
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
            # Note: removes all tracks linked to the genome
            delete_tracks(subdir)
        for file in os.listdir(f"{data_dir}/{subdir}"):
            if file.endswith(".bb") or file.endswith(".bw"):
                match_template(subdir, file)


# 1) Option B: use the list of tracks from command-line args
def process_track_list() -> None:
    """
    Processes a list of genomes, track tempaltes and/or datafiles to generate track payloads.
    Forwards the list of genomes and track templates to the `match_template` function for further processing.
    """

    global templates
    if args.templates:
        templates = [
            t for t in templates if any(t.startswith(i) for i in args.templates)
        ]
    files = args.templates or args.files
    total = len(args.genomes)
    for i, genome_id in enumerate(args.genomes):
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


# 2) Load the payload template(s) for each track type (datafile name)
def match_template(genome_id: str, datafile: str) -> None:
    """
    Matches a datafile to corresponding track template(s) and forwards it together with 
        the input genome ID (and the datafile name when needed) to `apply_template` function.
    Args:
        genome_id (str): UUID of the genome currently being processed.
        datafile (str): The name of the datafile currently being processed.
    Behavior:
        - Skips datafiles that are not in the input args (if provided),
            do not have a dedicated track entry ("variant-details", "*-summary"),
            or do not have a matching template (prints a warning).
        - Handles these matching scenarios in the following order:
            - Exact match between the datafile name and a template name:
              single track is submitted per datafile.
            - Partial match for templates starting with the datafile name:
              single datafile results in multiple tracks.
            - Partial match for datafiles starting with the template name:
              single datafile => single track, template matches different datafiles (fallback).
    """

    if args.files and not args.templates and datafile not in args.files:
        return
    filename = os.path.splitext(datafile)[0]
    # skip datafiles without dedicated track record in Track API: 
    # variant focus tracks, zoom-out view (only zoom-in view datafile is processed)
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
        # template matches a datafile with different suffix (e.g. repeats.repeatmask*.bb)
        if not multimatch and filename.startswith(template_name):
            apply_template(genome_id, template_name, datafile)
            return
    # unexpected datafile
    if not multimatch:
        log(f"Warning: No track template found for {datafile}")


# 3) Fill in the template (update variable fields/placeholders)
def apply_template(genome_id: str, template_name: str, datafile: str = "") -> None:
    """
    Updates a track template to generate track payload for a given genome/track.

    Args:
        genome_id (str): Genome UUID being processed.
        template_name (str): The name of the template file (without extension) being used.
        datafile (str, optional): Name of a datafile to override the one in the template (if given). 

    Notes:
        - Uses the `genome_id` field in the track template.
        - Updates the `datafile` field(s) in the track template when needed.
        - Updates species-specific fields for gene and variation tracks.
        - Submits the generated track data payload using the `submit_track` function.
    """
    with open(f"{template_dir}/{template_name}{EXT}", "r") as template_file:
        track_data: TrackData = yaml.safe_load(template_file)
    track_data["genome_id"] = genome_id  # always updated
    # update datafile field (when template matches multiple datafiles)
    if datafile:
        for key, value in track_data["datafiles"].items():
            # when the template defines a datafile pair for zoom-in/out views...
            if key.endswith("summary") and value: # empty value needs to stay empty
                # ...derive the zoom-out filename from the input (zoom-in) filename
                # e.g. variant-something-details.bb => variant-something-summary.bw
                nameroot = datafile[: datafile.rfind("-")]
                track_data["datafiles"][key] = f"{nameroot}-summary.bw"
            else: # use input datafile name as-is (single datafile or zoom-in view)
                track_data["datafiles"][key] = datafile
    # update species-specific template fields from metadata (for gene & variation tracks)
    if template_name.startswith("transcripts") or template_name.startswith("variant"):
        track_type = "gene" if template_name.startswith("transcripts") else "variant"
        if genome_id in metadata[track_type]:
            row = metadata[track_type][genome_id]
            if "track_name" in row and row["track_name"]:
                track_data["label"] = row["track_name"]
            if row["description"]:
                if track_type == "gene":
                    if row["source_names"][0]:
                        track_data[
                            "description"
                        ] += f"\nGenes {'annotated by' if row['description']=='Annotated' else 'imported from'}  {row['source_names'][0]}."
                else:
                    track_data["description"] = row["description"]
            if row["source_names"][0] and len(row["source_names"]) == len(row["source_urls"]):
                if "sources" not in track_data:
                    track_data["sources"] = []
                for i, source_name in enumerate(row["source_names"]):
                    if not source_name or not row["source_urls"][i]:
                        continue
                    track_data["sources"].append(
                        {"name": source_name, "url": row["source_urls"][i]}
                    )
        # every species is expected to have descriptions for its gene tracks in metadata
        elif track_type == "gene":
            log("Warning: Missing gene track descriptions.")
    # submit the track payload
    submit_track(track_data)


# 4) Submit the track payload to Track API
def submit_track(track_data: TrackData, second_try: bool = False) -> None:
    """
    Submits a complete track payload to the Track API.
    Args:
        track_data (TrackData): The track payload to be submitted.
        second_try (bool, optional): Indicates whether this is a retry attempt after a timeout.
    Notes:
        - If `--dryrun` flag is set in cli args, it logs the payload without submission.
        - Skips submission if the track already exists.
        - Logs the error and exits the script if submission fails for other reasons (e.g. server-side payload check).
    """

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

    # get gene/variant tracks metadata (species-specific track descriptions)
    # gene track metadata loaded from database, variant track data from CSV
    metadata["gene"] = get_gene_desc(release=args.release, genomes=args.genomes)
    metadata["variant"] = parse_csv(VARIANT_CSV_FILE)
    if not metadata["gene"]:
        genome_list = f" matching {', '.join(args.genomes)}" if args.genomes else ""
        fail(f"Error: No genomes found in release {args.release}{genome_list}.")
    # only consider genomes that are part of the specified release
    if not args.genomes:
        args.genomes = list(metadata["gene"].keys())
    else:
        unexpected_genomes = [g for g in args.genomes if g not in metadata["gene"]]
        if unexpected_genomes:
            fail(f"Error: These genomes are not part of release {args.release}: {', '.join(unexpected_genomes)}")

    if args.logfile:
        try:
            logfile = open(args.logfile, "w")
        except IOError as e:
            log(f"Warning: cannot open logfile {args.logfile}: {e}")

    # run the track loading process
    if track_api_url:
        log(f"Submitting tracks to {track_api_url}")
    if args.genomes and (args.files or args.templates):
        process_track_list()
    elif data_dir:
        process_data_dir()
    else:
        fail("Please provide either a data directory or a list of tracks (genomes+template names) to be loaded.")
    if logfile:
        logfile.close()
