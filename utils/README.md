## Bulk data updater for Track API

The `submit_tracks.py` script constructs and submits track payloads to the Track API `POST` endpoint to add new track records.
It uses the yaml templates in `/templates` and some supplemental data to construct the payloads (see below for more details).
The only required parameters are `--release` (release id) and `--env` (environment name, defaults to 'dev').
`--release` sets the list of genomes to be loaded, and `--env` sets the path to track datafiles dir and Track API endpoint URL.
The list of submitted genomes and tracks can also be specified with `--genomes`, `--templates` and `--files` params.
The data directory path and Track API URL values derived from `--env` can be overridden with environment variables, in which case the `--env` param can be omitted (see the example below).

### Track template selection and filling
The script infers the list of tracks to submit for each genome from the datafile names in the data dir, matching the name of datafiles (with `.bb` or `.bw` file extension) to corresponding template filenames as follows: 
- exact match: single template per datafile (e.g. `gc` track)
- template name starts with datafile name: multiple tracks per datafile (e.g. 4 gene tracks from `transcripts.bb`)
- datafile name starts with template name: fallback template (e.g. `variant.yaml` template is used for all `variant*.bb` datafiles that don't have exact template match like `variant-eva-details`)

The datafile directory path can be replaced with an explicit list of template and/or datafile names via `--templates` or `--files`. Note that in this case the script doesn't check the presence of datafiles.

For most cases the track template (i.e. track type, derived from the datafile name) define all the necessary fields in the track payload. The fields/values in the template (e.g. track label, category, description etc.) can be changed by updating the template in the github repo. An exception is the description field for gene and variation tracks, which varies depending on the species and is populated at the time of track submission from the Metadata DB (see `get_gene_desc.py`) or a CSV file (`/templates/variant-track-desc.csv`).

Example:
```bash
export TRACK_DATA_DIR=/Users/Alice/datafiles # override track datafiles location
export TRACK_API_URL=http://localhost:8000 # override target track API URL
./utils/submit_tracks.py --release 5 #submit all tracks for this relase to local endpoint
```
For more detailed instructions for running the track loading script, refer to [ENSWEBSOPS-171](https://www.ebi.ac.uk/panda/jira/browse/ENSWEBSOPS-171).