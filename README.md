## Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl 2020 client.  
Expects: genome ID (URL param)  
Returns: list of track categories and tracks for a given genome (JSON)  
Reference dataset: ./data/track_categories.yaml

### Quick Start

1. Clone the repo:

- `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
- `$ cd ensembl-track-api`

2. Build the database:

- `$ docker-compose run web python manage.py make migrations`
- `$ docker-compose run web python manage.py migrate`
- `$ docker-compose run web python ./utils/import_data.py`

3. Start the endpoint:

- `$ docker-compose up` #add '-d' to run in background

3. Usage:

- `http://localhost:8000/track_categories/:genome_id` #e.g. /track_categories/homo_sapiens_GCA_000001405_28

4. Stop the endpoint:

- `$ docker-compose down` #or Crtl+C if running in foreground

### CI/CD and Kubernetes deployment

The GitLab CI/CD configuration file and the Kubernetes manifests in `k8s` dir define the deployment accross 2 clusters and 4 namespaces.
For each of the 8 environments, 5 manifest files are applied to deploy the app:
- Applied manually: configmap.yaml, app_service.yaml, db_service_(cluster).yaml, ingress_(namespace).yaml
- Applied by CI/CD jobs: deployment.yaml, ingress_dev.yaml (only for review app)

The data is served from a dedicated postgres database in both k8s clusters (defined in `db_service_(cluster).yaml`).
Since the database user for k8s cluster is read-only, the database building is done from a local computer with a read/write database user.
Follow the quick start guide above and don't forget to grant access to the r/o user (see `utils/grant_access.sh`). 