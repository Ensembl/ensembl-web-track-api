#! /usr/bin/env python3

import sys
import json
import requests

track_api_url = 'http://staging.ensembl.org/api/tracks/track'

def submit_track(track_data):
  request_data = json.dumps(track_data)
  request = requests.post(f"{track_api_url}/track", data=request_data)
  if request.status_code != 200:
    print(f"Error submitting track ({request.status_code}): {request.content}")
    print(f"Payload: {request_data}")
    exit(1)
  print(request.content) #expected response: {"track_id": "some-uuid"}

mode = sys.argv[1] if len(sys.argv) > 1 else None
input = sys.argv[2] if len(sys.argv) > 2 else None

if(mode == 'variation'):
  if not input or not input.endswith('.json'):
    print('Input JSON file missing')
    exit(1)
  with open(input) as f:
    input_data = json.load(f)

  print(f"Submitting {len(input_data)} variation tracks:")  
  for uuid in input_data:
    print(f"Species {uuid}")
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
    submit_track(variation_track)
elif(mode == 'genomic'):
  input = sys.argv[2]
  if not input or not input.endswith('.csv'):
    print('Input CSV file missing')
    exit(1)
  print("Submitting genomic tracks:")
  with open(input) as f:
    header = True
    for line in f:
      if header:
        header = False
        continue
      line = line.strip()
      if not line:
        continue
      fields = line.split(',')
      if len(fields) != 8:
        print(f"Invalid line in input CSV: {line}")
        exit(1)
      print(f"Species {fields[2]}")
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
        "description": "Shows the contigs underlying the reference assembly",
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
  print('Not implemented yet')
elif(mode == 'remove'):
  if not input:
    print('Species UUID missing')
    exit(1)
  request = requests.delete(f"{track_api_url}/track_categories/{input}")
  if(request.status_code == 200):
    print(f"Removed tracks for species {input}")
  else:
    print(f"Error removing tracks for species {input} ({request.status_code}): {request.content}")
    exit(1)
else:
  print(f"Usage: {sys.argv[0]} <mode> <input>")
  print("Examples: variation input.json / genomic input.csv / regulation / remove <species_uuid>")
  exit(1)