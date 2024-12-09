## Utility scripts

### Bulk data updater

`submit_track_templates.py` script constructs and submits track payloads to Track API `POST` endpoint to add new tracks.
It uses the yaml templates in `/templates` to fill the payload fields. You specify the submitted track types (templates) with  `--template` parameter, 
or by pointing it to a data directory (by setting `TRACK_API_DIR` environment variable). In the latter case the script tries to sync the data directory
to Track API by matching each datafile (with `.bb`, `.bw` extension) with corresponding template file: a template filename must match or start with the datafile name to be submitted.
The datafile parent directory names are used to fill in the genome UUID field (override via `--genome` param).

Examples:
```bash
export TRACK_API_URL=http://localhost:8000 # target track API
export TRACK_DATA_DIR=/Users/Alice/datafiles # track datafiles

```

### Legacy scripts

