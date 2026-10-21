# Ensembl Track API

Django REST service providing track metadata for Ensembl clients and the Genome
Browser. Track records, specifications and dataset/release mappings are stored in SQLite.

## API

Paths below are relative to the service root (`/api/tracks` in Ensembl deployments).
See the [OpenAPI specification](ensembl-track-api.openapi.yaml) for parameters and payloads.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/track_categories/{genome_id}` | Categories and discoverable tracks for a genome |
| GET | `/configuration/{genome_id}/transcriptomic` | Transcriptomic selections, hierarchy, filters and counts for the client |
| GET | `/track/{track_id}` | Rendering metadata for one track (for Genome Browser) |
| GET | `/track?track_ids={uuid},{uuid}` | Rendering metadata for multiple tracks |
| POST | `/tracks/create` | Create a track from registered specifications |
| POST | `/tracks/link_type` | Link another specification to a track |

## Local development

Requires Python 3.10 or later. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

The service uses `db.sqlite3` by default; set `DATABASE_PATH` to use another database.
Migrations create the schema, but does not populate the track records. Use an existing
track catalogue or the [track loader](src/ensembl/production/tracks/load_tracks.py).
The `populate_dataset_releases` management command loads dataset/release mappings;
run it with `--help` for options.

Response caching is disabled by default. To enable it, set `ENABLE_CACHE=true` and
`REDIS_URL`; `CACHE_TTL` controls expiry. Other settings include
`DJANGO_ALLOWED_HOSTS`, `DJANGO_DEBUG` and `ALLOWED_METHODS` (default `get`).

Alternatively, `docker compose up --build` starts the API on port 8000 and Redis,
using `.env` and the mounted `db.sqlite3`, and applies migrations automatically.
Stop it with `docker compose down`.

Run tests with `python -m pytest`; the tests mock Redis and do not require a server.

## Transcriptomic PoC

Run-level RNA-seq coverage selections are grouped by tissue and sample. The client
configuration contains selection/filter metadata and track UUIDs; Genome Browser
loads datafiles and renderer settings through the single or bulk track endpoint.

The `seed_transcriptomic_configuration` management command prepares the transcriptomic track catalogue from the Genebuild handover JSON. Run
`python manage.py seed_transcriptomic_configuration --help` for options.
