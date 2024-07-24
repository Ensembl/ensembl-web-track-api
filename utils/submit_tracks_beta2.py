#!/usr/bin/env python3

import argparse
import glob
import os.path
import requests
from uuid import UUID
import yaml

args = argparse.Namespace()
template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")

def process_input_parameters():
  parser = argparse.ArgumentParser(description='Submit tracks to Track API based on input datafiles')
  parser.add_argument('-e', '--env', choices=['local', 'dev', 'staging', 'prod'],
                      default='dev', help='target Track API deployment (default: %(default)s)')
  parser.add_argument('-g', '--genome', nargs='*', metavar='GENOME_UUID', help='limit to specific genomes')
  parser.add_argument('-f', '--file', nargs='*', metavar='FILENAME', help='limit to specific tracks (datafiles)')
  parser.add_argument('-t', '--template', nargs='*', metavar='TEMPLATE', help='limit to specific track template')
  parser.add_argument('-d', '--dry-run', action='store_true', help='do not submit tracks, just print them')
  parser.add_argument('data_dir', metavar='DATA_DIR', help='root directory containing the datafiles (in genome subdirectories)')
  #repeat tracks: /hps/nobackup/flicek/ensembl/infrastructure/repeats-beta/results
  #other genomic tracks: /hps/nobackup/flicek/ensembl/infrastructure/arne/e2020-datafile-2024-03
  parser.parse_args(namespace=args)

# 1) Loop through all the available bigbed/bigwig datafiles
def process_bigbeds(root_dir: str) -> None:
  if not os.path.isdir(root_dir):
    print(f"Error: data directory {root_dir} not found")
    exit(1)
  for subdir in os.listdir(root_dir):
    if not os.path.isdir(f"{root_dir}/{subdir}"):
      continue
    try:
      UUID(subdir, version=4)
    except ValueError:
      print(f"Skipping non-genome directory {subdir}")
      continue
    if args.genome and subdir not in args.genome:
      continue
    print(f"Processing genome {subdir}")
    for file in os.listdir(f"{root_dir}/{subdir}"):
      if file.endswith('.bb') or file.endswith('.bw'):
        find_template(subdir, file)

# 2) Load the corresponding track payload template
def find_template(genome_id: str, datafile: str) -> None:
  if args.file and datafile not in args.file:
    return
  filename = os.path.splitext(datafile)[0]
  template_files = [os.path.basename(f) for f in glob.glob(f"{template_dir}/*.yaml")]
  if filename in template_files: # 1-to-1 match
    return apply_template(genome_id, datafile, filename)
  for template_file in template_files: # multiple tracks (templates) per datafile
    if template_file.startswith(filename):
      return apply_template(genome_id, datafile, template_file)

# 3) Fill in the template
def apply_template(genome_id: str, filename: str, template_file: str) -> None:
  if args.template and template_file not in args.template:
    return
  print(f"{filename} => {template_file}")
  with open(f"{template_dir}/{template_file}", 'r') as file:
    track_data: dict = yaml.safe_load(file)
  track_data['genome_id'] = genome_id
  submit_track(track_data)

# 4) Submit the track payload to Track API
def submit_track(track_data: dict, second_try: bool = False) -> None:
  print(f"Submitting track: {track_data['label']}")
  if args.dry_run:
    print(track_data)
    return

  track_api_url = f"https://{args.env}-2020.ensembl.org/api/tracks"
  try:
    request = requests.post(f"{track_api_url}/track", json=track_data)
  except requests.exceptions.ConnectTimeout:
    if (second_try):
      print("No luck, bailing out.")
      exit(1)
    else:
      print("Connection timed out. Retrying...")
      submit_track(track_data, True)

  msg = request.content.decode()
  if request.status_code != 201:
    if 'Track already exists' in msg:
      print(f"Track {track_data['trigger'][-1]} already exists, skipping.")
      return
    print(f"Error submitting track ({request.status_code}): {msg}")
    print(f"Track payload: {track_data}")
    exit(1)
  print(msg)  # expected response: {"track_id": "some-uuid"}

if __name__ == '__main__':
  process_input_parameters()
  process_bigbeds(args.data_dir)
