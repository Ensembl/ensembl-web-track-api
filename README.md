## Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl 2020 client.
Expects: genome ID (URL param)
Returns: list of track categories and tracks for a given genome (JSON)
Sample dataset: ./data/track_categories.yaml

### Quick Start

1. Start the endpoint:
- `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
- `$ cd ensembl-track-api`
- `$ sudo docker-compose -f docker-compose.yml up` #add '-d' to run in background

2. Build the database:
- `$ sudo docker-compose run web python manage.py makemigrations`
- `$ sudo docker-compose run web python manage.py migrate`
- `$ sudo docker-compose run web python import_data.py`

3. Use the endpoint:
- `http://0.0.0.0:8000/tracks/<genome_id>` #e.g. /tracks/homo_sapiens_GCA_000001405_28

4. Stop the endpoint:
- `$ sudo docker-compose -f docker-compose.yml down`
 