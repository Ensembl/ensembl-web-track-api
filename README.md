## Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl 2020 client.  
Expects: genome ID (URL param)  
Returns: list of track categories and tracks for a given genome (JSON)  
Reference dataset: ./data/track_categories.yaml

### Quick Start

1. Clone the repo:

- `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
- `$ cd ensembl-track-api`

2. Build the database (only needs to be done once):

- `$ docker-compose run web python manage.py migrate`
- `$ docker-compose run web python ./utils/import_data.py`

3. Start the endpoint:

- `$ docker-compose up` #add '-d' to run in background

3. Usage:

- `http://localhost:8000/track_categories/<genome_id>` #e.g. /track_categories/homo_sapiens_GCA_000001405_28

4. Stop the endpoint:

- `$ docker-compose down` #or Crtl+C if running in foreground
