## Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl 2020 client.  
Expects: genome ID (URL param)  
Returns: list of track categories and tracks for a given genome (JSON)  
Current dataset: ./data/track_categories.yaml

### Quick Start

1. Start the endpoint:

- `$ git clone https://gitlab.ebi.ac.uk/andres/ensembl-track-api.git`
- `$ cd ensembl-track-api`
- `$ docker-compose -f docker-compose.yaml up` #add '-d' to run in background

2. Build the database (on first startup only):

- `$ docker-compose run web python manage.py migrate`
- `$ docker-compose run web python import_data.py`

3. Use the endpoint:

- `http://localhost:8000/tracks_list/<genome_id>` #e.g. /tracks_list/homo_sapiens_GCA_000001405_28

4. Stop the endpoint:

- `$ docker-compose -f docker-compose.yaml down`
