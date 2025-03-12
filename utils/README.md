## Bulk data updater for Track API

`submit_tracks.py` script constructs and submits track payloads to Track API `POST` endpoint to add new tracks.
It uses the yaml templates in `/templates` and some supplemental data (from metadata db, csv files and track datafile directory) to construct the payloads.
The only required params are `--release` (release id) and `--env` (environment name, defaults to 'dev').
`--release` sets the list of genomes to be loaded, and `--env` sets the track datafiles dir (for list of track types to be loaded) and Track API endpoint URL.
The genomes list can be trimmed down with `--genomes` param, and the list of loaded track types with `--templates`.
The datadir path and Track API URL set can be overriden with envvars (see below).
Unless `--templates` is set, the script infers the list of tracks for each genome from the datafile names in the data dir. More specifically, it matches each datafile (with `.bb`, `.bw` extension) with corresponding template file: a template filename must match or start with the datafile name to be submitted.

Example:
```bash
export TRACK_DATA_DIR=/Users/Alice/datafiles # override track datafiles location
export TRACK_API_URL=http://localhost:8000 # override target track API
./utils/submit_tracks.py --release 5 #submit tracks the genomes in the release
```
For more detailed instructions for production, refer to [ENSWEBSOPS-171](https://www.ebi.ac.uk/panda/jira/browse/ENSWEBSOPS-171).

#### Note:
For some some tracks, species-specific values are used to fill out templates (e.g. track descriptions).

Data sources:
* Gene tracks: metadata API (using `get_gene_desc.py`)
* Variation tracks: `/templates/variant-track-desc.csv` (manually updated by Variation)