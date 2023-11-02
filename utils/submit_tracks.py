#! /usr/bin/env python3

import sys
import json
import requests

track_api_root = 'http://submit-tracks.review.ensembl.org/api/tracks'

def submit_track(track_data):
  request = requests.post(f"{track_api_root}/track", json=track_data)
  if request.status_code != 201:
    print(f"Error submitting track ({request.status_code}): {request.content}")
    print(f"Payload: {track_data}")
    exit(1)
  print(request.content.decode()) #expected response: {"track_id": "some-uuid"}

def parse_csv(path):
  if not path or not path.endswith('.csv'):
    print('Input CSV file missing')
    exit(1)
  with open(path) as f:
    lines = f.readlines()
  lines.pop(0) #remove header
  return [line.strip().split(',') for line in lines]

mode, input = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else (None, None)

if(mode == 'variation'):
  if not input or not input.endswith('.json'):
    print('Input JSON file missing')
    exit(1)
  with open(input) as f:
    input_data = json.load(f)

  print(f"Submitting {len(input_data)} variation tracks:")  
  for uuid in input_data:
    print(f"Species {uuid}:")
    for field in ['label','datafiles','description','source']:
      if field not in input_data[uuid] or not input_data[uuid][field]:
        print(f"Missing field in input JSON: {uuid}->{field}")
        exit(1)
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
    if len(fields) < 8:
      print(f"Invalid line in input CSV ({len(fields)} fields): {fields}")
      exit(1)
    print(f"Species {fields[2]}:")
    method = 'annotated by' if fields[4] == 'Annotated' else 'imported from'
    gene_pc_fwd = {
      "genome_id": fields[2],
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
      "description": f"Genes {method} {fields[3]}",
      "sources": [{ "name": fields[3], "url": fields[5] }]
    }
    submit_track(gene_pc_fwd)
    gene_pc_rev = {
      **gene_pc_fwd,
      "trigger": ["track","gene-pc-rev"],
      "additional_info": "Reverse strand",
      "display_order": 100
    }
    submit_track(gene_pc_rev)
    gene_other_fwd = {
      **gene_pc_fwd,
      "trigger": ["track","gene-other-fwd"],
      "label": "Other genes",
      "display_order": -100,
      "colour": "DARK_GREY"
    }
    submit_track(gene_other_fwd)
    gene_other_rev = {
      **gene_other_fwd,
      "trigger": ["track","gene-other-rev"],
      "additional_info": "Reverse strand",
      "display_order": 110
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
      "sources": []
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
    if len(fields) < 8:
      print(f"Invalid line in input CSV ({len(fields)} fields): {fields}")
      exit(1)
    print(f"Species {fields[0]}")
    reg_track = {
      "genome_id": fields[0],
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
    print('Species UUID missing')
    exit(1)
  request = requests.delete(f"{track_api_root}/track_categories/{input}")
  if(request.status_code == 204):
    print(f"Removed tracks for species {input}")
  else:
    print(f"Error removing tracks for species {input} ({request.status_code}): {request.content}")
    exit(1)
else:
  print(f"Usage: {sys.argv[0]} <mode> <input>")
  print(f"Example args: variation input.json / genomic input.csv / regulation input.csv / delete some-species-uuid")
  exit(1)