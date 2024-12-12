## Utility scripts

### Bulk data updater

`submit_track_templates.py` script constructs and submits track payloads to Track API `POST` endpoint to add new tracks.
It uses the yaml templates in `/templates` to fill the payload fields. You specify the submitted track types (templates) with  `--template` parameter, 
or by pointing it to a data directory (by setting `TRACK_API_DIR` environment variable). In the latter case the script tries to sync the data directory
to Track API by matching each datafile (with `.bb`, `.bw` extension) with corresponding template file: a template filename must match or start with the datafile name to be submitted.
The datafile parent directory names are used to fill in the genome UUID field (override via `--genome` param).

Example:
```bash
export TRACK_API_URL=http://localhost:8000 # target track API
export TRACK_DATA_DIR=/Users/Alice/datafiles # track datafiles
./utils/submit_track_templates.py #submit tracks for all datafiles in data dir
```
For more detailed instructions for production, refer to [ENSWEBSOPS-171](https://www.ebi.ac.uk/panda/jira/browse/ENSWEBSOPS-171).


#### Notes
Data submission script combines input from multiple sources:
| Source | Where | Why |
|-------|-------|------|
| Templates | `/tempaltes/*.yaml` | Track payload base |
| Overrides | `/tempaltes/*.csv` | Species-specific values |
| Datafiles | Input data dir | Specify species/tracks to submit |

The datafiles source can be replaced/modified with command-line params (`-g`,`-t`).

### Legacy scripts
Scripts kept for historical record, safe to be be removed.
- import_data.py: legacy data importer script; useful as an example of updating tracks database through Django datamodels 
- grant_access.sh: useful when read/write database users don't have a shared db schema
- submit_tracks_241: initial track submission script