import os
import glob
import requests
import yaml

# 1) Loop through all the available bigbed/bigwig datafiles
def process_bigbeds(root_dir):
  for subdir, dirs, files in os.walk(root_dir):
    for file in files:
      if file.endswith('.bb') or file.endswith('.bw'):
        find_template(subdir, file)

# 2) Read the corresponding track payload template
def find_template(genome_id, datafile):
  print(f"Processing {genome_id}/{datafile}")
  filename = os.path.splitext(datafile)[0]
  if filename in template_files:
    return apply_template(genome_id, datafile, filename)
  for template_file in template_files:
    if template_file.startswith(f"{filename}_"):
      return apply_template(genome_id, datafile, template_file)

# 3) Fill in the template
def apply_template(genome_id, filename, template_file):
  print(f"Applying {template_file} to {genome_id}/{filename}")
  with open(template_file, 'r') as file:
    track_data = yaml.safe_load(file)
  track_data['genome_id'] = genome_id
  submit_track(track_data)

# 4) Submit the track payload to Track API
def submit_track(track_data, retry=False):
  print(f"Submitting track {track_data['label']}")
  try:
    request = requests.post(f"{track_api_url}/track", json=track_data)
  except requests.exceptions.ConnectTimeout:
    if (retry):
      print(f"No luck, bailing out.")
      exit(1)
    else:
      print(f"Connection timed out. Retrying...")
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


data_root_dir = "/hps/nobackup/flicek/ensembl/infrastructure/repeats-beta/results" # repeat tracks
#data_root_dir = "/hps/nobackup/flicek/ensembl/infrastructure/arne/e2020-datafile-2024-03" # other genomic tracks
template_files = [os.path.basename(f) for f in glob.glob("../templates/*.yaml")]
track_api_url = f"https://dev-2020.ensembl.org/api/tracks"
process_bigbeds(data_root_dir)
