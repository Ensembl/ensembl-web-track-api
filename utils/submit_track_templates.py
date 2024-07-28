#!/usr/bin/env python3

import argparse
import glob
import os.path
import requests
from uuid import UUID
import yaml

args = argparse.Namespace()
template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
track_api_url = os.environ.get("TRACK_API_URL", "")
data_dir = os.environ.get("TRACK_DATA_DIR", "")

def process_input_parameters():
  global args, track_api_url, data_dir
  parser = argparse.ArgumentParser(
    description="Submit tracks to Track API based on input datafiles",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog='''
Required environment variables: 
  - TRACK_API_URL: Track API root address (e.g. https://dev-2020.ensembl.org/api/tracks)
  - TRACK_DATA_DIR: Directory containing the datafiles (in genome ID subdirectories)
    TRACK_DATA_DIR is optional if explicit track list is given with -g + -f or -t (skips datafile checks).

Examples:
  - Submit all tracks in TRACK_DATA_DIR (skipping already existing tracks): submit_tracks.py
  - Replace all tracks in reference Pig with a GC% track: submit_tracks.py -g a7335667-93e7-11ec-a39d-005056b38ce3 -t gc -o
  - Submit all four gene tracks for all genomes: submit_tracks.py -f transcripts.bb
  ''')
  parser.add_argument("-g", "--genome", nargs="*", metavar="GENOME_ID", help="limit to specific genomes")
  parser.add_argument("-f", "--file", nargs="*", metavar="FILENAME", help="limit to specific track datafiles")
  parser.add_argument("-t", "--template", nargs="*", metavar="TEMPLATE", help="limit to specific track templates")
  parser.add_argument("-q", "--quiet", action="store_true", help="suppress status messages")
  group = parser.add_mutually_exclusive_group()
  group.add_argument("-d", "--dry-run", action="store_true", help="do not submit tracks, just print the payload")
  group.add_argument("-o", "--overwrite", action="store_true", help="overwrite (all) existing tracks")
 
  parser.parse_args(namespace=args)
  if not track_api_url:
    print("Error: TRACK_API_URL environment variable not set")
    exit(1)
  if not data_dir and not (args.genome and (args.file or args.template)):
    print("Error: TRACK_DATA_DIR environment variable not set")
    exit(1)

def log(msg: str) -> None:
  if not args.quiet:
    print(msg)

# 1) Loop through all the available bigbed/bigwig datafiles
def process_data_dir() -> None:
  if not os.path.isdir(data_dir):
    print(f"Error: data directory {data_dir} not found")
    exit(1)
  subdirs = os.listdir(data_dir)
  for i, subdir in enumerate(subdirs):
    if not os.path.isdir(f"{data_dir}/{subdir}"):
      continue
    try:
      UUID(subdir, version=4)
    except ValueError:
      log(f"Skipping non-genome directory {subdir} ({i+1}/{len(subdirs)})")
      continue
    if args.genome and subdir not in args.genome:
      continue
    log(f"Processing genome {subdir} ()")
    if args.overwrite: # delete existing tracks first
      delete_tracks(subdir)
    for file in os.listdir(f"{data_dir}/{subdir}"):
      if file.endswith(".bb") or file.endswith(".bw"):
        match_template(subdir, file)

# 1b) Use a list of file/template names instead of data directory
def process_track_list() -> None:
  files = args.template or args.file
  for i, genome_id in enumerate(args.genome):
      log(f"Processing genome {genome_id} ({i+1}/{len(args.genome)})")
      if args.overwrite: # delete existing tracks first
        delete_tracks(genome_id)
      for filename in files:
        match_template(genome_id, filename)

# 2) Load the corresponding track payload template(s)
def match_template(genome_id: str, datafile: str) -> None:
  if args.file and not args.template and datafile not in args.file:
    return
  filename = os.path.splitext(datafile)[0]
  template_files = [os.path.basename(f) for f in glob.glob(f"{template_dir}/*.yaml")]
  if f"{filename}.yaml" in template_files: # 1-to-1 match
    apply_template(genome_id, filename)
    return
  for template_file in template_files: # multiple tracks (templates) per datafile
    if template_file.startswith(filename):
      apply_template(genome_id, template_file)

# 3) Fill in the template
def apply_template(genome_id: str, template_file: str) -> None:
  if args.template and template_file not in args.template:
    return
  if(not template_file.endswith(".yaml")):
    template_file += ".yaml"
  with open(f"{template_dir}/{template_file}", "r") as file:
    track_data: dict = yaml.safe_load(file)
  track_data['genome_id'] = genome_id
  submit_track(track_data)

# 4) Submit the track payload to Track API
def submit_track(track_data: dict, second_try: bool = False) -> None:
  log(f"Submitting track: {track_data['label']}")
  if args.dry_run:
    print(track_data)
    return
  
  try:
    request = requests.post(f"{track_api_url}/track", json=track_data)
  except requests.exceptions.ConnectTimeout:
    if (second_try):
      log("No luck, bailing out.")
      exit(1)
    else:
      log("Connection timed out. Retrying...")
      submit_track(track_data, True)

  msg = request.content.decode()
  if request.status_code != 201:
    if "Track already exists" in msg:
      log("Track already exists, skipping.")
      return
    print(f"Error submitting track ({request.status_code}): {msg}")
    print(f"Track payload: {track_data}")
    exit(1)
  log(msg)  # expected response: {"track_id": "some-uuid"}

def delete_tracks(genome_id: str) -> None:
  if args.dry_run:
    log(f"Deleting tracks for genome {genome_id}")
    return
  request = requests.delete(f"{track_api_url}/track_categories/{genome_id}")
  if request.status_code != 204:
    print(f"Error deleting tracks for genome {genome_id}: {request.content.decode()}")
    exit(1)

if __name__ == "__main__":
  process_input_parameters()
  if data_dir:
    process_data_dir()
  else:
    process_track_list()
