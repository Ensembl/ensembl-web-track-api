# Track API endpoint

REST service providing genome browser track data for [Ensembl Beta](https://beta.ensembl.org).

## REST API endpoints

REST API supports viewing/adding/removing tracks and track categories.

Example query (get the list of available tracks for human): https://beta.ensembl.org/api/tracks/track_categories/a7335667-93e7-11ec-a39d-005056b38ce3

See the [OpenAPI specification](https://editor.swagger.io/?url=https://raw.githubusercontent.com/Ensembl/ensembl-web-track-api/refs/heads/dev/ensembl-track-api.openapi.yaml) (source file [here](https://github.com/Ensembl/ensembl-web-track-api/blob/dev/ensembl-track-api.openapi.yaml)) for more examples and details.

## Quickstart on local machine

1. Clone the repo:

    - `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
    - `$ cd ensembl-track-api`
    - `pip install -e ".[dev]"`

2. Build the database:

    - `$ docker-compose run web python manage.py makemigrations`
    - `$ docker-compose run web python manage.py migrate`
    - `$ ./utils/submit_track_templates.py -t transcripts -g [genome_id]`

    See below for more information.

3. Start the service:

    - `$ docker-compose up` #add '-d' to run in background

4. Usage:

    - `http://localhost:8000/track_categories/:genome_id`

5. Stop the service:
    - `$ docker-compose down` #or Crtl+C if running in foreground

### Data updates

The `track/:track_id` REST endpoint supports `DELETE`/`POST` requests for adding/removing track entries. 
For bulk/automated updates, use `./utils/submit_tracks.py` script. See the accompanied readme for more details.


