# Track API endpoint

REST service providing genome browser track data for [Ensembl Beta](https://www.ensembl.org).

## REST API endpoints

REST API supports viewing/adding/removing tracks and track categories.

Example query (get the list of available tracks for human): https://www.ensembl.org/api/tracks/track_categories/a7335667-93e7-11ec-a39d-005056b38ce3

See the [OpenAPI specification](https://editor.swagger.io/?url=https://raw.githubusercontent.com/Ensembl/ensembl-web-track-api/refs/heads/dev/ensembl-track-api.openapi.yaml) (source file [here](https://github.com/Ensembl/ensembl-web-track-api/blob/dev/ensembl-track-api.openapi.yaml)) for more examples and details.

## Quickstart on local machine

1. Clone the repo:

    - `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
    - `$ cd ensembl-track-api`
    - `$ pip install -e ".[dev]"` # installs dependencies from pyproject.toml

2. Build the database:

    - `$ docker compose run web python manage.py makemigrations`
    - `$ docker compose run web python manage.py migrate`
    - `$ ./utils/submit_track_templates.py -t transcripts -g [genome_id]`

    See below for more information.

3. Start the service:

    - `$ docker compose up` #add '-d' to run in background

4. Usage:

    - `http://localhost:8000/track_categories/:genome_id`

5. Stop the service:
    - `$ docker compose down` #or Ctrl+C if running in foreground

### Allowed HTTP methods

`ALLOWED_METHODS` controls which HTTP methods the API permits. When unset, it defaults to `get` (read-only).

Values are comma-separated and case-insensitive; surrounding whitespace is ignored. Only get, post and delete are accepted. Empty values, empty entries and unsupported methods prevent application startup.
Each endpoint retains its own method restrictions. Excluded methods return HTTP 405 before the endpoint handler runs. HEAD and OPTIONS are unsupported and return HTTP 405; GET does not implicitly enable HEAD.

### Data updates

The following endpoints modify track data and require their HTTP method to be enabled in `ALLOWED_METHODS`:

| Method | Endpoint | Operation |
| --- | --- | --- |
| POST | `/tracks/create` | Create a track |
| POST | `/tracks/link_type` | Link an additional type to a track |
| DELETE | `/track/{track_id}` | Delete a track |
| DELETE | `/track_categories/{genome_id}` | Delete all tracks for a genome |
