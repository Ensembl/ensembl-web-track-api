#! /usr/bin/env python3

import sys
import json
import requests

def print_help(msg=None):
  if(msg):
    print(msg)
  print(f"""Usage: {sys.argv[0]} <env> <mode> [input]
  env: staging | beta | review-app-name
  mode: variation | genomic | regulation | delete
  input: path to JSON file (variation) or CSV file (genomic/regulation) or genome UUID (delete)""")
  exit(1)

def parse_csv(path):
  if not path or not path.endswith('.csv'):
    print_help('Input CSV file missing')

  with open(path) as f:
    lines = f.readlines()
  lines.pop(0) #remove header
  return [line.strip().split(',') for line in lines]

env, mode, input = (sys.argv[1], sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else print_help()

if(env == 'beta'):
  prefix = 'https://beta'
elif(env == 'staging'):
  prefix = 'https://staging-2020'
else:
  prefix = f"http://{env}.review"

track_api_root = f"{prefix}.ensembl.org/api/tracks"
print(f"Submitting tracks to {track_api_root}")

def submit_track(track_data, retry=False):
  try:
    request = requests.post(f"{track_api_root}/track", json=track_data)
  except requests.exceptions.ConnectTimeout:
    if(retry):
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
  print(msg) #expected response: {"track_id": "some-uuid"}

if(mode == 'variation'):
  if not input or not input.endswith('.json'):
    print_help('Input JSON file missing')

  with open(input) as f:
    input_data = json.load(f)

  print(f"Submitting {len(input_data)} variation tracks:")  
  for uuid in input_data:
    print(f"Genome {uuid}:")
    for field in ['label','datafiles','description','source']:
      if field not in input_data[uuid] or not input_data[uuid][field]:
        print(f"Missing field in input JSON: {field}. Skipping genome {uuid}.")
        continue

    variation_track = {
      **input_data[uuid],
      "genome_id": uuid,
      "category": {
        "track_category_id": "short-variants",
        "label": "Short variants by resource",
        "type": "Variation"
      },
      "trigger": ["track","expand-variation"],
      "type": "variant",
      "display_order": 1000,
      "on_by_default": True
    }
    variation_track['sources'] = [variation_track.pop('source')]
    submit_track(variation_track)

elif(mode == 'genomic'):
  lines = parse_csv(input)
  print(f"Submitting {len(lines)*6} genomic tracks:")
  for fields in lines:
    uuid = fields[2] if len(fields)>2 else ''
    if len(fields) < 8 or not uuid:
      print(f"Invalid line in input CSV ({len(fields)} fields): {fields}")
      print(f"Skipping genome {uuid}")
      continue

    print(f"Genome {uuid}:")
    method = f"Genes {'annotated by' if fields[4]=='Annotated' else 'imported from'} {fields[3]}"
    gene_pc_fwd = {
      "genome_id": uuid,
      "label": "Protein coding genes",
      "category": {
        "track_category_id": "genes-transcripts",
        "label": "Genes & transcripts",
        "type": "Genomic"
      },
      "trigger": ["track","gene-pc-fwd"],
      "type": "gene",
      "colour": "DARK_GREY",
      "additional_info": "Forward strand",
      "display_order": -110,
      "on_by_default": True,
      "datafiles": {},
      "description": f"Shows all protein coding genes on the forward strand.\n{method}",
      "sources": [{ "name": fields[3], "url": fields[5] }]
    }
    submit_track(gene_pc_fwd)

    gene_pc_rev = {
      **gene_pc_fwd,
      "trigger": ["track","gene-pc-rev"],
      "additional_info": "Reverse strand",
      "display_order": 100,
      "description": f"Shows all protein coding genes on the reverse strand.\n{method}"
    }
    submit_track(gene_pc_rev)

    gene_other_fwd = {
      **gene_pc_fwd,
      "trigger": ["track","gene-other-fwd"],
      "label": "Other genes",
      "display_order": -100,
      "colour": "GREY",
      "description": f"Shows all non-coding genes on the forward strand.\n{method}"
    }
    submit_track(gene_other_fwd)

    gene_other_rev = {
      **gene_other_fwd,
      "trigger": ["track","gene-other-rev"],
      "additional_info": "Reverse strand",
      "display_order": 110,
      "description": f"Shows all non-coding genes on the reverse strand.\n{method}"
    }
    submit_track(gene_other_rev)

    seq = {
      **gene_pc_fwd,
      "label": "Reference sequence",
      "category": {
        "track_category_id": "assembly",
        "label": "Assembly",
        "type": "Genomic"
      },
      "trigger": ["track","contig"],
      "type": "regular",
      "display_order": 0,
      "description": "Displays the sequence underlying the assembly",
      "sources": [],
      "colour": "",
      "additional_info": ""
    }
    submit_track(seq)

    gc = {
      **seq,
      "label": "%GC",
      "trigger": ["track","gc"],
      "display_order": 900,
      "description": "Shows the percentage of Gs and Cs in a region"
    }
    submit_track(gc)

elif(mode == 'regulation'):
  lines = parse_csv(input)
  print(f"Submitting {len(lines)} regulation tracks:")

  for fields in lines:
    uuid = fields[0] if len(fields) else ''
    if len(fields) < 8 or not uuid:
      print(f"Invalid line in input CSV ({len(fields)} fields): {fields}")
      print(f"Skipping genome {uuid}")
      continue

    print(f"Genome {uuid}")
    reg_track = {
      "genome_id": uuid,
      "label": "Regulatory annotation",
      "category": {
        "track_category_id": "regulatory-features",
        "label": "Regulation",
        "type": "Regulation"
      },
      "trigger": ["track","regulation"],
      "type": "regular",
      "datafiles": { "bigbed": "regulatory-features.bb" },
      "display_order": 890,
      "on_by_default": True,
      "description": """Promoters, enhancers and open chromatin regions are available for all species. 
      Transcription factor binding and CTCF binding sites are only available for human and mouse.""", #from ENSWBSITES-1969
      "sources": []
    }
    submit_track(reg_track)

elif(mode == 'delete'):
  if not input:
    print_help('Genome UUID missing')

  request = requests.delete(f"{track_api_root}/track_categories/{input}")
  if(request.status_code == 204):
    print(f"Removed tracks for genome {input}")
  else:
    print(f"Error removing tracks for genome {input} ({request.status_code}): {request.content}")
    exit(1)

else:
  print_help(f"Unknown mode: {mode}")